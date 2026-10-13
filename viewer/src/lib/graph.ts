// Graph tab model: graphify's graph/graph.json (networkx node-link format:
// {nodes: [{id, label, community, community_name, source_file, source_location…}],
//  links|edges: [{source, target, relation…}]}) mapped to repo files and filtered
// for Cytoscape. The format is owned by graphify, so every field is optional here.

export interface GNode {
  id: string;
  label: string;
  /** Community id as a string ("" when the node has none). */
  community: string;
  /** Repo-relative path of the node's source file, when it is in tree.json. */
  path: string | null;
  /** 1-based line of the node in that file. */
  line: number | null;
}

export interface GEdge {
  id: string;
  source: string;
  target: string;
  relation?: string;
}

export interface Community {
  id: string;
  name: string;
  count: number;
  color: string;
}

export interface GraphModel {
  nodes: GNode[];
  edges: GEdge[];
  communities: Community[];
}

export const MAX_NODES = 800;

// Distinguishable hues that read on light and dark backgrounds.
const PALETTE = [
  '#4e79a7',
  '#f28e2b',
  '#e15759',
  '#76b7b2',
  '#59a14f',
  '#edc948',
  '#b07aa1',
  '#ff9da7',
  '#9c755f',
  '#8cd17d',
  '#499894',
  '#d37295',
];

function colorFor(i: number): string {
  if (i < PALETTE.length) return PALETTE[i];
  // beyond the palette: spread hues with the golden angle
  return `hsl(${Math.round((i * 137.508) % 360)}, 55%, 55%)`;
}

/**
 * Map a graphify source-file attribute to a tree.json path: backslashes become
 * "/", "./" and duplicate slashes are dropped; absolute (or otherwise prefixed)
 * paths match by their longest suffix that is a repo path. null when unknown.
 */
export function normalizeSourcePath(src: unknown, paths: Set<string>): string | null {
  if (typeof src !== 'string' || src.trim() === '') return null;
  const segs = src
    .trim()
    .replace(/\\/g, '/')
    .split('/')
    .filter((s) => s !== '' && s !== '.');
  for (let i = 0; i < segs.length; i++) {
    const cand = segs.slice(i).join('/');
    if (paths.has(cand)) return cand;
  }
  return null;
}

/** Line of a source_location such as "L12" or "L3-9"; null when absent or invalid. */
export function parseLine(loc: unknown): number | null {
  if (typeof loc === 'number') return Number.isInteger(loc) && loc > 0 ? loc : null;
  if (typeof loc !== 'string') return null;
  const m = /^\s*L?(\d+)/.exec(loc);
  const n = m ? Number(m[1]) : 0;
  return n > 0 ? n : null;
}

function idOf(v: unknown): string | null {
  if (typeof v === 'string' || typeof v === 'number') return String(v);
  if (v && typeof v === 'object' && 'id' in v) return idOf((v as { id: unknown }).id);
  return null;
}

function asRecords(v: unknown): Record<string, unknown>[] {
  return Array.isArray(v) ? v.filter((x): x is Record<string, unknown> => !!x && typeof x === 'object') : [];
}

/** Parse graph.json against the snapshot's file paths. */
export function parseGraph(raw: unknown, paths: Set<string>): GraphModel {
  const obj = raw && typeof raw === 'object' ? (raw as Record<string, unknown>) : {};
  const nodes: GNode[] = [];
  const known = new Set<string>();
  const names = new Map<string, string>();
  const counts = new Map<string, number>();
  for (const n of asRecords(obj.nodes)) {
    const id = idOf(n.id);
    if (id === null || known.has(id)) continue;
    known.add(id);
    const community = n.community === undefined || n.community === null ? '' : String(n.community);
    if (typeof n.community_name === 'string' && n.community_name && !names.has(community)) {
      names.set(community, n.community_name);
    }
    counts.set(community, (counts.get(community) ?? 0) + 1);
    const label = typeof n.label === 'string' && n.label ? n.label : typeof n.name === 'string' && n.name ? n.name : id;
    nodes.push({
      id,
      label,
      community,
      path: normalizeSourcePath(n.source_file ?? n.file ?? n.path, paths),
      line: parseLine(n.source_location ?? n.line),
    });
  }

  const edges: GEdge[] = [];
  const rawEdges = Array.isArray(obj.links) ? obj.links : obj.edges;
  asRecords(rawEdges).forEach((e, i) => {
    const source = idOf(e.source);
    const target = idOf(e.target);
    if (source === null || target === null || !known.has(source) || !known.has(target)) return;
    const edge: GEdge = { id: `e${i}`, source, target };
    if (typeof e.relation === 'string') edge.relation = e.relation;
    edges.push(edge);
  });

  // Numeric communities in numeric order, then named ones, "no community" last.
  const ids = [...counts.keys()].sort((a, b) => {
    if (a === '' || b === '') return a === '' ? 1 : -1;
    const na = Number(a);
    const nb = Number(b);
    if (!Number.isNaN(na) && !Number.isNaN(nb)) return na - nb;
    return a < b ? -1 : a > b ? 1 : 0;
  });
  const communities = ids.map((id, i) => ({
    id,
    name: names.get(id) ?? (id === '' ? 'Sin comunidad' : `Comunidad ${id}`),
    count: counts.get(id)!,
    color: colorFor(i),
  }));
  return { nodes, edges, communities };
}

export interface Selection {
  nodes: GNode[];
  edges: GEdge[];
  /** Nodes matching the filters before the cap. */
  total: number;
  truncated: boolean;
}

/**
 * Nodes of the selected communities matching the text filter (label or path,
 * case-insensitive), capped at `limit` (nodes of the focused file first), plus
 * the edges between them.
 */
export function selectElements(
  g: GraphModel,
  opts: { communities: Set<string>; text: string; focus?: string; limit?: number },
): Selection {
  const q = opts.text.trim().toLowerCase();
  const limit = opts.limit ?? MAX_NODES;
  let matching = g.nodes.filter(
    (n) =>
      opts.communities.has(n.community) &&
      (!q || n.label.toLowerCase().includes(q) || (n.path !== null && n.path.toLowerCase().includes(q))),
  );
  const total = matching.length;
  if (opts.focus) {
    const f = opts.focus;
    matching = [...matching.filter((n) => n.path === f), ...matching.filter((n) => n.path !== f)];
  }
  const nodes = matching.slice(0, limit);
  const ids = new Set(nodes.map((n) => n.id));
  const edges = g.edges.filter((e) => ids.has(e.source) && ids.has(e.target));
  return { nodes, edges, total, truncated: total > nodes.length };
}
