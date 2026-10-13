// Ctrl+K search: a client-side index of tree paths, symbol definitions and
// explanation block titles, ranked by a small subsequence score.

import type { Route } from './router';
import type { Explain, SearchEntry, Symbols, Tree } from './types';

export interface SearchItem {
  kind: 'file' | 'symbol' | 'block';
  /** Text the query is matched against (and shown as the label). */
  text: string;
  detail?: string;
  route: Route;
}

function isBoundary(text: string, i: number): boolean {
  if (i === 0) return true;
  const prev = text[i - 1];
  if (/[\s/_.\-:#()]/.test(prev)) return true;
  // camelCase: lower → upper
  return prev === prev.toLowerCase() && prev !== prev.toUpperCase() && text[i] !== text[i].toLowerCase();
}

/**
 * Score of `query` as a case-insensitive subsequence of `text` (null = no match).
 * Each matched char scores 1, +5 when it continues the previous match, +4 at a
 * word start; the result is the best over every start position of the first
 * char, minus a small penalty for the text length.
 */
export function fuzzyScore(query: string, text: string): number | null {
  const q = query.toLowerCase();
  if (q === '') return 0;
  const t = text.toLowerCase();
  let best: number | null = null;
  for (let start = t.indexOf(q[0]); start !== -1; start = t.indexOf(q[0], start + 1)) {
    let score = 0;
    let ti = start;
    let prev = -2;
    let ok = true;
    for (let qi = 0; qi < q.length; qi++) {
      const at = qi === 0 ? start : t.indexOf(q[qi], ti);
      if (at === -1) {
        ok = false;
        break;
      }
      score += 1;
      if (at === prev + 1) score += 5;
      if (isBoundary(text, at)) score += 4;
      prev = at;
      ti = at + 1;
    }
    if (!ok) break; // later starts cannot match either
    if (best === null || score > best) best = score;
  }
  return best === null ? null : best - text.length * 0.01;
}

/** Best `limit` items for the query (score desc, then shorter text). */
export function rankItems(items: SearchItem[], query: string, limit = 50): SearchItem[] {
  const q = query.trim();
  if (!q) return [];
  const scored: { item: SearchItem; score: number }[] = [];
  for (const item of items) {
    const score = fuzzyScore(q, item.text);
    if (score !== null) scored.push({ item, score });
  }
  scored.sort((a, b) => b.score - a.score || a.item.text.length - b.item.text.length);
  return scored.slice(0, limit).map((s) => s.item);
}

export function fileItems(tree: Tree, study: string, sha: string): SearchItem[] {
  return tree.files.map((f) => ({ kind: 'file', text: f.path, detail: f.language ?? undefined, route: { kind: 'file', study, sha, path: f.path } }));
}

export function symbolItems(symbols: Symbols, study: string, sha: string): SearchItem[] {
  const out: SearchItem[] = [];
  for (const [path, fs] of Object.entries(symbols.files)) {
    for (const d of fs.defs) {
      out.push({
        kind: 'symbol',
        text: d.name,
        detail: `${d.kind} · ${path}:${d.range[0]}`,
        route: { kind: 'file', study, sha, path, range: { start: d.range[0], end: d.range[1] } },
      });
    }
  }
  return out;
}

export function blockItems(explain: Explain, study: string, sha: string): SearchItem[] {
  return explain.blocks.map((b) => ({
    kind: 'block',
    text: b.title,
    detail: `${explain.path}:${b.range[0]}-${b.range[1]}`,
    route: { kind: 'file', study, sha, path: explain.path, range: { start: b.range[0], end: b.range[1] } },
  }));
}

/** Block items from search.json (same items as blockItems over every explanation). */
export function searchEntryItems(entries: SearchEntry[], study: string, sha: string): SearchItem[] {
  return entries.map((e) => ({
    kind: 'block',
    text: e.title,
    detail: `${e.path}:${e.range[0]}-${e.range[1]}`,
    route: { kind: 'file', study, sha, path: e.path, range: { start: e.range[0], end: e.range[1] } },
  }));
}

/**
 * Append-only list of search items: `add` pushes in place (amortized O(1) per
 * item, no copy of what is already there) and bumps `version`, which callers
 * can track to know when `items` changed.
 */
export class SearchIndex {
  readonly items: SearchItem[] = [];
  version = 0;

  add(more: readonly SearchItem[]): void {
    if (more.length === 0) return;
    for (const item of more) this.items.push(item);
    this.version++;
  }
}

/**
 * Run `fn` over `items` with at most `limit` in flight, reporting each result
 * as it arrives. Failed tasks are skipped; `cancelled()` stops scheduling.
 */
export async function mapLimit<T, R>(
  items: T[],
  limit: number,
  fn: (item: T) => Promise<R>,
  onResult?: (result: R, item: T) => void,
  cancelled: () => boolean = () => false,
): Promise<void> {
  let next = 0;
  async function worker() {
    while (next < items.length && !cancelled()) {
      const item = items[next++];
      try {
        const r = await fn(item);
        if (!cancelled()) onResult?.(r, item);
      } catch {
        // skip: the index is best-effort
      }
    }
  }
  await Promise.all(Array.from({ length: Math.min(limit, items.length) }, worker));
}

/** What loadBlockItems needs from StudyData (a subset, so tests can fake it). */
export interface BlockSource {
  search(sha: string): Promise<SearchEntry[] | null>;
  explain(sha: string, path: string): Promise<Explain | null>;
}

/**
 * Block items of a snapshot, reported through `onItems` as they become available.
 * Uses search.json when the kb has it (a single request; resolves 'index');
 * otherwise (missing or failing) fetches every file's explanation, `limit` at a
 * time, reporting each one's blocks and the files still pending (resolves 'files').
 */
export async function loadBlockItems(
  src: BlockSource,
  tree: Tree,
  study: string,
  sha: string,
  onItems: (items: SearchItem[]) => void,
  opts: { cancelled?: () => boolean; onPending?: (n: number) => void; limit?: number } = {},
): Promise<'index' | 'files'> {
  const cancelled = opts.cancelled ?? (() => false);
  let entries: SearchEntry[] | null = null;
  try {
    entries = await src.search(sha);
  } catch {
    entries = null;
  }
  if (cancelled()) return entries ? 'index' : 'files';
  if (entries) {
    onItems(searchEntryItems(entries, study, sha));
    return 'index';
  }
  // every file may have an explanation (also non-indexed ones such as README.md)
  let pending = tree.files.length;
  opts.onPending?.(pending);
  await mapLimit(
    tree.files,
    opts.limit ?? 6,
    (f) =>
      src.explain(sha, f.path).finally(() => {
        if (!cancelled()) opts.onPending?.(--pending);
      }),
    (ex) => {
      if (ex) onItems(blockItems(ex, study, sha));
    },
    cancelled,
  );
  return 'files';
}
