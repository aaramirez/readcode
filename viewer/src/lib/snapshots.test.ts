import { describe, expect, it } from 'vitest';
import { routeOnSnapshotSwitch } from './snapshots';
import type { Tree } from './types';

const NEW = 'd'.repeat(40);
const OLD = 'e'.repeat(40);

const tree: Tree = {
  schemaVersion: 1,
  sha: NEW,
  files: ['app/main.py', 'app/services/billing.py', 'README.md'].map((path) => ({
    path,
    blob: 'h',
    language: null,
    lines: 1,
    bytes: 1,
    indexed: true,
  })),
  excluded: [],
};

describe('routeOnSnapshotSwitch', () => {
  it('keeps a file (and its range) that exists in the new tree', () => {
    const r = routeOnSnapshotSwitch({ kind: 'file', study: 's', sha: OLD, path: 'app/main.py', range: { start: 3 } }, NEW, tree);
    expect(r).toEqual({ route: { kind: 'file', study: 's', sha: NEW, path: 'app/main.py', range: { start: 3 } }, notice: null });
  });

  it('goes to the overview with a notice when the file is gone', () => {
    const r = routeOnSnapshotSwitch({ kind: 'file', study: 's', sha: OLD, path: 'db/queries.sql' }, NEW, tree);
    expect(r.route).toEqual({ kind: 'overview', study: 's', sha: NEW });
    expect(r.notice).toContain('db/queries.sql');
    expect(r.notice).toContain('ddddddd');
  });

  it('keeps directories that still contain files, and the root', () => {
    expect(routeOnSnapshotSwitch({ kind: 'dir', study: 's', sha: OLD, path: 'app/services' }, NEW, tree).route).toEqual({
      kind: 'dir',
      study: 's',
      sha: NEW,
      path: 'app/services',
    });
    expect(routeOnSnapshotSwitch({ kind: 'dir', study: 's', sha: OLD, path: '' }, NEW, tree).route.kind).toBe('dir');
    const gone = routeOnSnapshotSwitch({ kind: 'dir', study: 's', sha: OLD, path: 'db' }, NEW, tree);
    expect(gone.route.kind).toBe('overview');
    expect(gone.notice).toContain('db/');
    // "app" must not match "application/…"
    expect(routeOnSnapshotSwitch({ kind: 'dir', study: 's', sha: OLD, path: 'ap' }, NEW, tree).route.kind).toBe('overview');
  });

  it('falls back to the overview when the new tree is missing', () => {
    const r = routeOnSnapshotSwitch({ kind: 'file', study: 's', sha: OLD, path: 'app/main.py' }, NEW, null);
    expect(r.route.kind).toBe('overview');
    expect(r.notice).not.toBeNull();
  });

  it('keeps a diff file as a file route of the new snapshot', () => {
    const r = routeOnSnapshotSwitch({ kind: 'diff', study: 's', a: OLD, b: NEW, path: 'README.md' }, NEW, tree);
    expect(r.route).toEqual({ kind: 'file', study: 's', sha: NEW, path: 'README.md' });
    expect(routeOnSnapshotSwitch({ kind: 'diff', study: 's', a: OLD, b: NEW }, NEW, tree).route.kind).toBe('overview');
  });

  it('keeps graph focus only when the file exists', () => {
    expect(routeOnSnapshotSwitch({ kind: 'graph', study: 's', sha: OLD, path: 'README.md' }, NEW, tree).route).toEqual({
      kind: 'graph',
      study: 's',
      sha: NEW,
      path: 'README.md',
    });
    expect(routeOnSnapshotSwitch({ kind: 'graph', study: 's', sha: OLD, path: 'gone.py' }, NEW, tree).route).toEqual({
      kind: 'graph',
      study: 's',
      sha: NEW,
    });
  });

  it('carries tours and diagrams over, everything else goes to the overview', () => {
    expect(routeOnSnapshotSwitch({ kind: 'tour', study: 's', sha: OLD, id: 't', step: 2 }, NEW, tree).route).toEqual({
      kind: 'tour',
      study: 's',
      sha: NEW,
      id: 't',
      step: 2,
    });
    expect(routeOnSnapshotSwitch({ kind: 'diagrams', study: 's', sha: OLD, name: 'x' }, NEW, tree).route).toMatchObject({ sha: NEW, name: 'x' });
    expect(routeOnSnapshotSwitch({ kind: 'overview', study: 's', sha: OLD }, NEW, tree)).toEqual({
      route: { kind: 'overview', study: 's', sha: NEW },
      notice: null,
    });
  });
});
