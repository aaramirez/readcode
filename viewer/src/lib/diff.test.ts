import { describe, expect, it } from 'vitest';
import { diffBadges, diffLinkSha, diffTree, hunkTarget } from './diff';
import type { Changes, Tree } from './types';

const A = 'a'.repeat(40);
const B = 'b'.repeat(40);
const H = (c: string) => c.repeat(64);

const changes: Changes = {
  schemaVersion: 1,
  from: A,
  to: B,
  files: [
    { path: 'app/billing.py', status: 'modified', fromBlob: H('1'), toBlob: H('2'), hunks: [{ fromRange: null, toRange: [11, 15] }] },
    { path: 'app/refunds.py', status: 'added', toBlob: H('3'), hunks: [] },
    { path: 'db/queries.sql', status: 'deleted', fromBlob: H('4'), hunks: [] },
    { path: 'web/new.ts', oldPath: 'web/old.ts', status: 'renamed', fromBlob: H('5'), toBlob: H('5'), hunks: [] },
  ],
};

function tree(sha: string, files: [string, string | null][]): Tree {
  return {
    schemaVersion: 1,
    sha,
    files: files.map(([path, language]) => ({ path, language, blob: H('0'), lines: 1, bytes: 1, indexed: true })),
    excluded: [],
  };
}

const treeA = tree(A, [
  ['app/billing.py', 'python'],
  ['db/queries.sql', 'sql'],
  ['web/old.ts', 'typescript'],
  ['README.md', 'markdown'],
]);
const treeB = tree(B, [
  ['app/billing.py', 'python'],
  ['app/refunds.py', 'python'],
  ['web/new.ts', 'typescript'],
  ['README.md', 'markdown'],
]);

describe('diffTree', () => {
  it('contains only changed files, in changes order', () => {
    const t = diffTree(changes, treeA, treeB);
    expect(t.files.map((f) => f.path)).toEqual(['app/billing.py', 'app/refunds.py', 'db/queries.sql', 'web/new.ts']);
    expect(t.excluded).toEqual([]);
    expect(t.sha).toBe(B);
  });

  it('takes languages from B, falling back to A (deleted / renamed)', () => {
    const t = diffTree(changes, treeA, treeB);
    expect(t.files.map((f) => f.language)).toEqual(['python', 'python', 'sql', 'typescript']);
  });

  it('works without trees', () => {
    const t = diffTree(changes, null, null);
    expect(t.files.every((f) => f.language === null)).toBe(true);
    expect(t.files).toHaveLength(4);
  });
});

describe('diffBadges', () => {
  it('maps statuses to A/M/D/R badges', () => {
    const b = diffBadges(changes);
    expect([...b.entries()].map(([p, v]) => [p, v.badge])).toEqual([
      ['app/billing.py', 'M'],
      ['app/refunds.py', 'A'],
      ['db/queries.sql', 'D'],
      ['web/new.ts', 'R'],
    ]);
    expect(b.get('web/new.ts')!.title).toContain('web/old.ts');
    expect(b.get('app/refunds.py')!.title).toBe('añadido');
  });
});

describe('diffLinkSha', () => {
  const inB = new Set(treeB.files.map((f) => f.path));
  const inA = new Set(treeA.files.map((f) => f.path));
  it('opens targets present in B in snapshot B', () => {
    expect(diffLinkSha('app/billing.py', inB, inA, A, B)).toBe(B);
  });
  it('falls back to A for targets only in A (deleted files)', () => {
    expect(diffLinkSha('db/queries.sql', inB, inA, A, B)).toBe(A);
  });
  it('defaults to B when the target is in neither tree', () => {
    expect(diffLinkSha('nope.py', inB, inA, A, B)).toBe(B);
    expect(diffLinkSha('app/billing.py', inB, inA, A, B, 'A')).toBe(A);
    expect(diffLinkSha('db/queries.sql', null, null, A, B)).toBe(B);
  });
});

describe('hunkTarget', () => {
  it('prefers the new side', () => {
    expect(hunkTarget({ fromRange: [3, 4], toRange: [5, 9] })).toEqual({ side: 'b', range: [5, 9] });
    expect(hunkTarget({ fromRange: null, toRange: [11, 15] })).toEqual({ side: 'b', range: [11, 15] });
  });
  it('uses the old side for pure deletions', () => {
    expect(hunkTarget({ fromRange: [2, 3], toRange: null })).toEqual({ side: 'a', range: [2, 3] });
  });
  it('returns null without ranges', () => {
    expect(hunkTarget({ fromRange: null, toRange: null })).toBeNull();
    expect(hunkTarget(undefined)).toBeNull();
  });
});
