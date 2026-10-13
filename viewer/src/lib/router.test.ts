import { describe, expect, it } from 'vitest';
import { format, latestSnapshot, parse, resolveSha, type Route } from './router';
import type { Study } from './types';

const SHA = 'b42f63fb2414b4d4d830af722a64255504a80ee8';
const SHA2 = '074ec965eabffb43a0224ef9f1426515d2818975';

describe('parse', () => {
  it.each<[string, Route]>([
    ['', { kind: 'catalog' }],
    ['#', { kind: 'catalog' }],
    ['#/', { kind: 'catalog' }],
    ['#/fixture', { kind: 'study', study: 'fixture' }],
    [`#/fixture/${SHA}/`, { kind: 'overview', study: 'fixture', sha: SHA }],
    [`#/fixture/${SHA}`, { kind: 'overview', study: 'fixture', sha: SHA }],
    ['#/fixture/b42f63f/', { kind: 'overview', study: 'fixture', sha: 'b42f63f' }],
    [`#/fixture/${SHA}/f/app/main.py`, { kind: 'file', study: 'fixture', sha: SHA, path: 'app/main.py' }],
    [
      `#/fixture/${SHA}/f/app/main.py:L42`,
      { kind: 'file', study: 'fixture', sha: SHA, path: 'app/main.py', range: { start: 42 } },
    ],
    [
      `#/fixture/${SHA}/f/app/main.py:L42-78`,
      { kind: 'file', study: 'fixture', sha: SHA, path: 'app/main.py', range: { start: 42, end: 78 } },
    ],
    [`#/fixture/${SHA}/d/`, { kind: 'dir', study: 'fixture', sha: SHA, path: '' }],
    [`#/fixture/${SHA}/d`, { kind: 'dir', study: 'fixture', sha: SHA, path: '' }],
    [`#/fixture/${SHA}/d/app/sub`, { kind: 'dir', study: 'fixture', sha: SHA, path: 'app/sub' }],
    [`#/fixture/${SHA}/tour/login`, { kind: 'tour', study: 'fixture', sha: SHA, id: 'login' }],
    [`#/fixture/${SHA}/tour/login/3`, { kind: 'tour', study: 'fixture', sha: SHA, id: 'login', step: 3 }],
    [`#/fixture/${SHA}/graph`, { kind: 'graph', study: 'fixture', sha: SHA }],
    [`#/fixture/${SHA}/graph/app/main.py`, { kind: 'graph', study: 'fixture', sha: SHA, path: 'app/main.py' }],
    [`#/fixture/${SHA}/diagrams`, { kind: 'diagrams', study: 'fixture', sha: SHA }],
    [`#/fixture/${SHA}/diagrams/arch`, { kind: 'diagrams', study: 'fixture', sha: SHA, name: 'arch' }],
    [`#/fixture/diff/${SHA}..${SHA2}`, { kind: 'diff', study: 'fixture', a: SHA, b: SHA2 }],
    [
      '#/fixture/diff/b42f63f..074ec96/app/main.py',
      { kind: 'diff', study: 'fixture', a: 'b42f63f', b: '074ec96', path: 'app/main.py' },
    ],
  ])('%s', (hash, route) => {
    expect(parse(hash)).toEqual(route);
  });

  it.each([
    'fixture',
    '#/fixture/xyz/',
    '#/fixture/abc12/',
    `#/fixture/${SHA}/zzz/x`,
    `#/fixture/${SHA}/f/`,
    `#/fixture/${SHA}/f/a//b`,
    `#/fixture/${SHA}/tour/login/0`,
    `#/fixture/${SHA}/tour/login/x`,
    `#/fixture/${SHA}/f/%E0%A4%A`,
    '#/fixture/diff/abc',
  ])('notfound: %s', (hash) => {
    expect(parse(hash).kind).toBe('notfound');
  });

  it('decodes encoded spaces, unicode and colons in paths', () => {
    expect(parse(`#/fixture/${SHA}/f/docs/mi%20archivo/se%C3%B1al%3Av2.ts:L3-4`)).toEqual({
      kind: 'file',
      study: 'fixture',
      sha: SHA,
      path: 'docs/mi archivo/señal:v2.ts',
      range: { start: 3, end: 4 },
    });
  });
});

describe('format / round-trip', () => {
  const routes: Route[] = [
    { kind: 'catalog' },
    { kind: 'study', study: 'fixture' },
    { kind: 'overview', study: 'fixture', sha: SHA },
    { kind: 'file', study: 'fixture', sha: SHA, path: 'app/main.py' },
    { kind: 'file', study: 'fixture', sha: SHA, path: 'app/main.py', range: { start: 1 } },
    { kind: 'file', study: 'fixture', sha: SHA, path: 'a b/ñandú 日本.py', range: { start: 2, end: 9 } },
    { kind: 'file', study: 'fixture', sha: SHA, path: 'weird:L5/x:L1-2.txt' },
    { kind: 'file', study: 'fixture', sha: SHA, path: 'q?#%&.md' },
    { kind: 'dir', study: 'fixture', sha: SHA, path: '' },
    { kind: 'dir', study: 'fixture', sha: SHA, path: 'con espacio/sub' },
    { kind: 'tour', study: 'fixture', sha: SHA, id: 'login' },
    { kind: 'tour', study: 'fixture', sha: SHA, id: 'recorrido inicial', step: 2 },
    { kind: 'graph', study: 'fixture', sha: SHA },
    { kind: 'graph', study: 'fixture', sha: SHA, path: 'app/año.py' },
    { kind: 'diagrams', study: 'fixture', sha: SHA },
    { kind: 'diagrams', study: 'fixture', sha: SHA, name: 'arquitectura general' },
    { kind: 'diff', study: 'fixture', a: SHA, b: SHA2 },
    { kind: 'diff', study: 'fixture', a: 'b42f63f', b: '074ec96', path: 'src/ü x.ts' },
  ];
  it.each(routes)('round-trips %j', (route) => {
    expect(parse(format(route))).toEqual(route);
  });

  it('formats canonical hashes', () => {
    expect(format({ kind: 'catalog' })).toBe('#/');
    expect(format({ kind: 'overview', study: 'fixture', sha: SHA })).toBe(`#/fixture/${SHA}/`);
    expect(format({ kind: 'dir', study: 'fixture', sha: SHA, path: '' })).toBe(`#/fixture/${SHA}/d/`);
    expect(
      format({ kind: 'file', study: 'fixture', sha: SHA, path: 'a b/c.py', range: { start: 42, end: 78 } }),
    ).toBe(`#/fixture/${SHA}/f/a%20b/c.py:L42-78`);
  });
});

describe('snapshots', () => {
  const study: Study = {
    schemaVersion: 1,
    name: 'fixture',
    title: 'Fixture',
    repo: { url: 'x' },
    language: 'es',
    exclude: [],
    tools: { graphify: false, archify: false },
    snapshots: [
      { sha: SHA2, date: '2026-01-11T10:00:00Z', message: 'b', status: 'partial' },
      { sha: SHA, date: '2026-01-10T10:00:00Z', message: 'a', status: 'partial' },
      { sha: 'b42f63fb0000000000000000000000000000000a', date: '2026-01-09T10:00:00Z', message: 'c', status: 'indexed' },
    ],
  };

  it('resolves unique prefixes', () => {
    expect(resolveSha(study, '074ec96')).toBe(SHA2);
    expect(resolveSha(study, SHA)).toBe(SHA);
    expect(resolveSha(study, 'b42f63fb2')).toBe(SHA);
  });

  it('returns null for unknown or ambiguous prefixes', () => {
    expect(resolveSha(study, 'b42f63f')).toBeNull();
    expect(resolveSha(study, 'fffffff')).toBeNull();
  });

  it('picks the latest snapshot by date', () => {
    expect(latestSnapshot(study)?.sha).toBe(SHA2);
    expect(latestSnapshot({ ...study, snapshots: [] })).toBeNull();
  });
});
