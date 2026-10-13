// Diff view helpers (diffs/<a>..<b>/changes.json).

import type { ChangeStatus, Changes, Hunk, Range, Tree } from './types';

export interface DiffBadge {
  badge: 'A' | 'M' | 'D' | 'R';
  status: ChangeStatus;
  title: string;
}

const BADGES: Record<ChangeStatus, DiffBadge['badge']> = { added: 'A', modified: 'M', deleted: 'D', renamed: 'R' };
const TITLES: Record<ChangeStatus, string> = {
  added: 'añadido',
  modified: 'modificado',
  deleted: 'eliminado',
  renamed: 'renombrado',
};

/** A tree.json-like view with only the changed files (for the file tree). */
export function diffTree(changes: Changes, treeA: Tree | null, treeB: Tree | null): Tree {
  const lang = new Map<string, string | null>();
  for (const f of treeA?.files ?? []) lang.set(f.path, f.language);
  for (const f of treeB?.files ?? []) lang.set(f.path, f.language);
  return {
    schemaVersion: 1,
    sha: changes.to,
    files: changes.files.map((c) => ({
      path: c.path,
      blob: c.toBlob ?? c.fromBlob ?? '',
      language: lang.get(c.path) ?? (c.oldPath ? lang.get(c.oldPath) : undefined) ?? null,
      lines: 0,
      bytes: 0,
      indexed: true,
    })),
    excluded: [],
  };
}

/** A/M/D/R badge per changed path. */
export function diffBadges(changes: Changes): Map<string, DiffBadge> {
  const out = new Map<string, DiffBadge>();
  for (const c of changes.files) {
    const title = c.status === 'renamed' && c.oldPath ? `renombrado desde ${c.oldPath}` : TITLES[c.status];
    out.set(c.path, { badge: BADGES[c.status], status: c.status, title });
  }
  return out;
}

/**
 * Snapshot a diff link target opens in: B when the file is in B's tree, else A
 * when it is in A's (e.g. a deleted file), else B (ruling 16).
 */
export function diffLinkSha(
  target: string,
  pathsB: Set<string> | null,
  pathsA: Set<string> | null,
  a: string,
  b: string,
): string {
  if (pathsB?.has(target)) return b;
  if (pathsA?.has(target)) return a;
  return b;
}

/** Where a hunk lives in the merge view: new side, or old side for pure deletions. */
export function hunkTarget(h: Hunk | undefined): { side: 'a' | 'b'; range: Range } | null {
  if (!h) return null;
  if (h.toRange) return { side: 'b', range: h.toRange };
  if (h.fromRange) return { side: 'a', range: h.fromRange };
  return null;
}
