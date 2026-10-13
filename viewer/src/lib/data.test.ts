import { describe, expect, it, vi } from 'vitest';
import { HttpError, KbClient } from './data';
import type { Links } from './types';

const SHA = 'b42f63fb2414b4d4d830af722a64255504a80ee8';

function mockFetch(files: Record<string, unknown>, statusFor: Record<string, number> = {}) {
  return vi.fn(async (url: string) => {
    if (statusFor[url]) return new Response('err', { status: statusFor[url] });
    if (!(url in files)) return new Response('404 Not Found', { status: 404 });
    const v = files[url];
    return new Response(typeof v === 'string' ? v : JSON.stringify(v), { status: 200 });
  });
}

describe('KbClient', () => {
  it('fetches the catalog and caches by URL', async () => {
    const f = mockFetch({ 'kb/catalog.json': { schemaVersion: 1, studies: [] } });
    const kb = new KbClient('kb/', f);
    const [a, b] = await Promise.all([kb.catalog(), kb.catalog()]);
    expect(a).toEqual({ schemaVersion: 1, studies: [] });
    expect(b).toBe(a);
    await kb.catalog();
    expect(f).toHaveBeenCalledTimes(1);
  });

  it('returns null on 404 (and caches it)', async () => {
    const f = mockFetch({});
    const s = new KbClient('kb/', f).study('fixture');
    expect(await s.overview(SHA)).toBeNull();
    expect(await s.explain(SHA, 'app/main.py')).toBeNull();
    expect(await s.overview(SHA)).toBeNull();
    expect(f).toHaveBeenCalledTimes(2);
  });

  it('throws on other errors and does not cache the failure', async () => {
    const f = mockFetch({}, { 'kb/fixture/study.json': 500 });
    const s = new KbClient('kb/', f).study('fixture');
    await expect(s.study()).rejects.toBeInstanceOf(HttpError);
    await expect(s.study()).rejects.toThrow('HTTP 500');
    expect(f).toHaveBeenCalledTimes(2);
  });

  it('builds kb paths for every resource', async () => {
    const f = mockFetch({});
    const s = new KbClient('kb/', f).study('fixture');
    await s.study();
    await s.tree(SHA);
    await s.symbols(SHA);
    await s.explain(SHA, 'app/mi archivo.py');
    await s.dir(SHA, '');
    await s.dir(SHA, 'app/sub');
    await s.overview(SHA);
    await s.links(SHA);
    await s.tour(SHA, 'login');
    await s.graph(SHA);
    await s.issues(SHA);
    await s.blob('3a898b6d25440f41e1dce7421361b9c67c67b89525235af1b7b45f2e81fd1938');
    await s.changes('aaa', 'bbb');
    await s.diffExplain('aaa', 'bbb');
    await s.diffFileExplain('aaa', 'bbb', 'app/x.py');
    expect(f.mock.calls.map((c) => c[0])).toEqual([
      'kb/fixture/study.json',
      `kb/fixture/snapshots/${SHA}/tree.json`,
      `kb/fixture/snapshots/${SHA}/symbols.json`,
      `kb/fixture/snapshots/${SHA}/explain/app/mi%20archivo.py.json`,
      `kb/fixture/snapshots/${SHA}/dirs/_root.json`,
      `kb/fixture/snapshots/${SHA}/dirs/app/sub.json`,
      `kb/fixture/snapshots/${SHA}/overview.md`,
      `kb/fixture/snapshots/${SHA}/links.json`,
      `kb/fixture/snapshots/${SHA}/tours/login.json`,
      `kb/fixture/snapshots/${SHA}/graph/graph.json`,
      `kb/fixture/snapshots/${SHA}/issues.json`,
      'kb/fixture/blobs/3a/3a898b6d25440f41e1dce7421361b9c67c67b89525235af1b7b45f2e81fd1938.txt',
      'kb/fixture/diffs/aaa..bbb/changes.json',
      'kb/fixture/diffs/aaa..bbb/explain.md',
      'kb/fixture/diffs/aaa..bbb/explain/app/x.py.json',
    ]);
  });

  it('returns text resources as text', async () => {
    const f = mockFetch({ [`kb/fixture/snapshots/${SHA}/overview.md`]: '# Hola' });
    expect(await new KbClient('kb/', f).study('fixture').overview(SHA)).toBe('# Hola');
  });

  describe('tours and diagrams lists from links.json', () => {
    const links: Links = {
      schemaVersion: 1,
      sha: SHA,
      docs: {
        'overview.md': [
          { raw: '[[archify:arquitectura]]', kind: 'archify', status: 'exact', target: 'diagrams/arquitectura.html' },
          { raw: '[[ref:app/main.py#main]]', kind: 'symbol', status: 'exact', target: 'app/main.py', range: [1, 3] },
        ],
        'tours/login.json': [],
        'tours/alta-usuario.json': [
          { raw: '[[archify:arquitectura]]', kind: 'archify', status: 'exact', target: 'diagrams/arquitectura.html' },
          { raw: '[[archify:flujo]]', kind: 'archify', status: 'exact', target: 'diagrams/flujo.html' },
          { raw: '[[archify:falta]]', kind: 'archify', status: 'broken' },
        ],
        'explain/app/tours/x.py.json': [],
        'dirs/_root.json': [],
      },
    };
    const setup = () => {
      const f = mockFetch({ [`kb/fixture/snapshots/${SHA}/links.json`]: links });
      return { f, s: new KbClient('kb/', f).study('fixture') };
    };

    it('derives tour ids from doc keys tours/<id>.json (even with zero markers)', async () => {
      const { s } = setup();
      expect(await s.tours(SHA)).toEqual([{ id: 'alta-usuario' }, { id: 'login' }]);
    });

    it('derives unique archify names, flagging broken ones', async () => {
      const { s } = setup();
      expect(await s.diagrams(SHA)).toEqual([
        { name: 'arquitectura', broken: false },
        { name: 'falta', broken: true },
        { name: 'flujo', broken: false },
      ]);
      expect(s.diagramUrl(SHA, 'flujo')).toBe(`kb/fixture/snapshots/${SHA}/diagrams/flujo.html`);
      expect(s.diagramUrl(SHA, '../x')).toBeNull();
      expect(s.diagramUrl(SHA, 'a/b')).toBeNull();
      expect(s.diagramUrl(SHA, String.raw`a\b`)).toBeNull();
    });

    it('shares one links.json request between both lists', async () => {
      const { f, s } = setup();
      await Promise.all([s.tours(SHA), s.diagrams(SHA), s.links(SHA)]);
      expect(f).toHaveBeenCalledTimes(1);
    });

    it('returns empty lists when links.json is missing', async () => {
      const s2 = new KbClient('kb/', mockFetch({})).study('fixture');
      expect(await s2.tours(SHA)).toEqual([]);
      expect(await s2.diagrams(SHA)).toEqual([]);
    });
  });
});
