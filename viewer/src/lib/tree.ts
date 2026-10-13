// Builds the file tree shown in the left pane from tree.json (directories are
// implied by file paths). Children are sorted: directories first, then files,
// each group alphabetically (case-insensitive, ties broken by code units).

import type { Tree } from './types';

export interface TreeNode {
  name: string;
  /** Repo path ("" for the root). */
  path: string;
  kind: 'dir' | 'file';
  children: TreeNode[];
  language?: string | null;
  /** True for paths listed in tree.json "excluded". */
  excluded?: boolean;
}

function compare(a: TreeNode, b: TreeNode): number {
  if (a.kind !== b.kind) return a.kind === 'dir' ? -1 : 1;
  const la = a.name.toLowerCase();
  const lb = b.name.toLowerCase();
  if (la !== lb) return la < lb ? -1 : 1;
  return a.name < b.name ? -1 : a.name > b.name ? 1 : 0;
}

function sortRec(node: TreeNode): void {
  node.children.sort(compare);
  for (const c of node.children) if (c.kind === 'dir') sortRec(c);
}

export function buildTree(tree: Tree, includeExcluded = false): TreeNode {
  const root: TreeNode = { name: '', path: '', kind: 'dir', children: [] };
  const dirs = new Map<string, TreeNode>([['', root]]);

  function dirFor(path: string, excluded: boolean): TreeNode {
    let node = dirs.get(path);
    if (node) return node;
    const cut = path.lastIndexOf('/');
    const parent = dirFor(cut < 0 ? '' : path.slice(0, cut), excluded);
    node = { name: path.slice(cut + 1), path, kind: 'dir', children: [] };
    if (excluded) node.excluded = true;
    parent.children.push(node);
    dirs.set(path, node);
    return node;
  }

  function add(path: string, leaf: Omit<TreeNode, 'name' | 'path' | 'kind' | 'children'>, excluded: boolean) {
    const cut = path.lastIndexOf('/');
    const parent = dirFor(cut < 0 ? '' : path.slice(0, cut), excluded);
    parent.children.push({ name: path.slice(cut + 1), path, kind: 'file', children: [], ...leaf });
  }

  for (const f of tree.files) add(f.path, { language: f.language }, false);
  if (includeExcluded) {
    for (const e of tree.excluded) {
      // An excluded entry may name a directory (e.g. "node_modules"); show it as a leaf.
      if (dirs.has(e.path)) continue;
      add(e.path, { excluded: true }, true);
    }
  }
  sortRec(root);
  return root;
}

/** Ancestor directory paths of a repo path, outermost first (excluding the root). */
export function ancestors(path: string): string[] {
  const parts = path.split('/');
  const out: string[] = [];
  for (let i = 1; i < parts.length; i++) out.push(parts.slice(0, i).join('/'));
  return out;
}

/**
 * Filter by case-insensitive substring of the path. Returns the pruned tree and
 * the set of directory paths to expand so every match is visible; null when the
 * filter is empty.
 */
export function filterTree(root: TreeNode, query: string): { root: TreeNode; expand: Set<string> } | null {
  const q = query.trim().toLowerCase();
  if (!q) return null;
  const expand = new Set<string>();
  function walk(node: TreeNode): TreeNode | null {
    if (node.kind === 'file') return node.path.toLowerCase().includes(q) ? node : null;
    const selfMatch = node.path !== '' && node.path.toLowerCase().includes(q);
    const kids = node.children.map(walk).filter((n): n is TreeNode => n !== null);
    if (kids.length === 0 && !selfMatch) return null;
    if (kids.length > 0) expand.add(node.path);
    return { ...node, children: selfMatch && kids.length === 0 ? node.children : kids };
  }
  return { root: walk(root) ?? { ...root, children: [] }, expand };
}
