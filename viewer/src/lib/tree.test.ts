import { describe, expect, it } from 'vitest';
import { ancestors, buildTree, filterTree, type TreeNode } from './tree';
import type { Tree, TreeFile } from './types';

const file = (path: string, language: string | null = 'python'): TreeFile => ({
  path,
  blob: '0'.repeat(64),
  language,
  lines: 1,
  bytes: 1,
  indexed: true,
});

const tree: Tree = {
  schemaVersion: 1,
  sha: 'b42f63fb2414b4d4d830af722a64255504a80ee8',
  files: [
    file('zeta.py'),
    file('app/models.py'),
    file('README.md', 'markdown'),
    file('app/main.py'),
    file('app/sub/deep/x.ts', 'typescript'),
    file('alpha/b.go', 'go'),
    file('.gitignore', null),
  ],
  excluded: [
    { path: 'node_modules', reason: 'default' },
    { path: 'app/data.bin', reason: 'binary' },
    { path: 'dist/out.js', reason: 'default' },
  ],
};

const shape = (n: TreeNode): unknown =>
  n.kind === 'file' ? n.name : { [n.name || '/']: n.children.map(shape) };

describe('buildTree', () => {
  it('implies directories and sorts dirs first, then files, alphabetically', () => {
    expect(shape(buildTree(tree))).toEqual({
      '/': [
        { alpha: ['b.go'] },
        { app: [{ sub: [{ deep: ['x.ts'] }] }, 'main.py', 'models.py'] },
        '.gitignore',
        'README.md',
        'zeta.py',
      ],
    });
  });

  it('keeps full paths and languages', () => {
    const root = buildTree(tree);
    const app = root.children.find((c) => c.name === 'app')!;
    expect(app.path).toBe('app');
    const deep = app.children[0].children[0];
    expect(deep.path).toBe('app/sub/deep');
    expect(deep.children[0]).toMatchObject({ path: 'app/sub/deep/x.ts', kind: 'file', language: 'typescript' });
  });

  it('adds excluded paths (greyed) only on request', () => {
    expect(buildTree(tree).children.some((c) => c.excluded)).toBe(false);
    const root = buildTree(tree, true);
    expect(shape(root)).toEqual({
      '/': [
        { alpha: ['b.go'] },
        { app: [{ sub: [{ deep: ['x.ts'] }] }, 'data.bin', 'main.py', 'models.py'] },
        { dist: ['out.js'] },
        '.gitignore',
        'node_modules',
        'README.md',
        'zeta.py',
      ],
    });
    const app = root.children.find((c) => c.name === 'app')!;
    expect(app.excluded).toBeUndefined();
    expect(app.children.find((c) => c.name === 'data.bin')!.excluded).toBe(true);
    expect(root.children.find((c) => c.name === 'dist')!.excluded).toBe(true);
  });
});

describe('filterTree', () => {
  it('returns null for an empty query', () => {
    expect(filterTree(buildTree(tree), '  ')).toBeNull();
  });

  it('keeps matches and expands their ancestors', () => {
    const r = filterTree(buildTree(tree), 'X.T')!;
    expect(shape(r.root)).toEqual({ '/': [{ app: [{ sub: [{ deep: ['x.ts'] }] }] }] });
    expect([...r.expand].sort()).toEqual(['', 'app', 'app/sub', 'app/sub/deep']);
  });
});

describe('ancestors', () => {
  it('lists parent dirs outermost first', () => {
    expect(ancestors('a/b/c.py')).toEqual(['a', 'a/b']);
    expect(ancestors('c.py')).toEqual([]);
  });
});
