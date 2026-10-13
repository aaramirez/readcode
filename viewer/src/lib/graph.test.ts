import { describe, expect, it } from 'vitest';
import { normalizeSourcePath, parseGraph, parseLine, selectElements } from './graph';

const PATHS = new Set(['app/main.py', 'app/models.py', 'web/src/api.ts', 'README.md']);

describe('normalizeSourcePath', () => {
  it('keeps repo-relative forward-slash paths', () => {
    expect(normalizeSourcePath('app/main.py', PATHS)).toBe('app/main.py');
  });
  it('normalizes backslashes and ./ prefixes', () => {
    expect(normalizeSourcePath('app\\main.py', PATHS)).toBe('app/main.py');
    expect(normalizeSourcePath('./web/src/api.ts', PATHS)).toBe('web/src/api.ts');
    expect(normalizeSourcePath('.\\web\\src\\api.ts', PATHS)).toBe('web/src/api.ts');
    expect(normalizeSourcePath('app//main.py', PATHS)).toBe('app/main.py');
  });
  it('maps absolute paths by their longest repo suffix', () => {
    expect(normalizeSourcePath('C:\\Users\\x\\repo\\app\\models.py', PATHS)).toBe('app/models.py');
    expect(normalizeSourcePath('/home/x/repo/README.md', PATHS)).toBe('README.md');
    expect(normalizeSourcePath('repo/app/main.py', PATHS)).toBe('app/main.py');
  });
  it('returns null for unknown files and non-strings', () => {
    expect(normalizeSourcePath('other/file.py', PATHS)).toBeNull();
    expect(normalizeSourcePath('', PATHS)).toBeNull();
    expect(normalizeSourcePath(undefined, PATHS)).toBeNull();
    expect(normalizeSourcePath(42, PATHS)).toBeNull();
  });
});

describe('parseLine', () => {
  it('reads L<n> and plain numbers', () => {
    expect(parseLine('L12')).toBe(12);
    expect(parseLine('L3-9')).toBe(3);
    expect(parseLine('7')).toBe(7);
    expect(parseLine(5)).toBe(5);
  });
  it('rejects garbage', () => {
    expect(parseLine('x')).toBeNull();
    expect(parseLine('L0')).toBeNull();
    expect(parseLine(null)).toBeNull();
  });
});

const RAW = {
  directed: false,
  nodes: [
    { id: 'n1', label: 'main()', community: 0, community_name: 'app', source_file: 'app/main.py', source_location: 'L4' },
    { id: 'n2', label: 'Invoice', community: 0, community_name: 'app', source_file: 'app\\models.py', source_location: 'L1' },
    { id: 'n3', label: 'fetchInvoice', community: 1, community_name: 'web', source_file: 'web/src/api.ts' },
    { id: 'n4', label: 'external', community: 2, source_file: 'elsewhere/x.py' },
    { id: 5, label: 'loose' },
  ],
  links: [
    { source: 'n1', target: 'n2', relation: 'calls' },
    { source: 'n3', target: 'n2', relation: 'uses' },
    { source: 'n1', target: 'missing' },
    { source: 'n4', target: 5 },
  ],
};

describe('parseGraph', () => {
  const g = parseGraph(RAW, PATHS);

  it('maps nodes to files and lines', () => {
    expect(g.nodes).toHaveLength(5);
    expect(g.nodes[0]).toMatchObject({ id: 'n1', label: 'main()', community: '0', path: 'app/main.py', line: 4 });
    expect(g.nodes[1]).toMatchObject({ path: 'app/models.py', line: 1 });
    expect(g.nodes[2]).toMatchObject({ path: 'web/src/api.ts', line: null });
    expect(g.nodes[3]).toMatchObject({ path: null, community: '2' });
    expect(g.nodes[4]).toMatchObject({ id: '5', label: 'loose', community: '' });
  });

  it('keeps only edges between known nodes', () => {
    expect(g.edges.map((e) => [e.source, e.target])).toEqual([
      ['n1', 'n2'],
      ['n3', 'n2'],
      ['n4', '5'],
    ]);
    expect(g.edges[0].relation).toBe('calls');
    expect(new Set(g.edges.map((e) => e.id)).size).toBe(3);
  });

  it('lists communities with names, counts and distinct colors', () => {
    expect(g.communities.map((c) => [c.id, c.name, c.count])).toEqual([
      ['0', 'app', 2],
      ['1', 'web', 1],
      ['2', 'Comunidad 2', 1],
      ['', 'Sin comunidad', 1],
    ]);
    expect(new Set(g.communities.map((c) => c.color)).size).toBe(4);
  });

  it('accepts "edges" and endpoint objects', () => {
    const g2 = parseGraph({ nodes: [{ id: 'a' }, { id: 'b' }], edges: [{ source: { id: 'a' }, target: { id: 'b' } }] }, PATHS);
    expect(g2.edges).toHaveLength(1);
  });

  it('tolerates malformed input', () => {
    expect(parseGraph(null, PATHS).nodes).toEqual([]);
    expect(parseGraph({ nodes: 'x' }, PATHS).nodes).toEqual([]);
  });
});

describe('selectElements', () => {
  const g = parseGraph(RAW, PATHS);
  const all = new Set(g.communities.map((c) => c.id));

  it('filters by community and drops dangling edges', () => {
    const s = selectElements(g, { communities: new Set(['0']), text: '' });
    expect(s.nodes.map((n) => n.id)).toEqual(['n1', 'n2']);
    expect(s.edges).toHaveLength(1);
    expect(s.truncated).toBe(false);
    expect(s.total).toBe(2);
  });

  it('filters by text over label and path (case-insensitive)', () => {
    expect(selectElements(g, { communities: all, text: 'INVOICE' }).nodes.map((n) => n.id)).toEqual(['n2', 'n3']);
    expect(selectElements(g, { communities: all, text: 'api.ts' }).nodes.map((n) => n.id)).toEqual(['n3']);
  });

  it('caps the node count, keeping focused file nodes first', () => {
    const s = selectElements(g, { communities: all, text: '', limit: 2, focus: 'web/src/api.ts' });
    expect(s.truncated).toBe(true);
    expect(s.total).toBe(5);
    expect(s.nodes.map((n) => n.id)).toEqual(['n3', 'n1']);
  });

  it('uses 800 as the default cap', () => {
    const nodes = Array.from({ length: 900 }, (_, i) => ({ id: `x${i}`, community: 0 }));
    const big = parseGraph({ nodes, links: [] }, PATHS);
    const s = selectElements(big, { communities: new Set(['0']), text: '' });
    expect(s.nodes).toHaveLength(800);
    expect(s.truncated).toBe(true);
  });
});
