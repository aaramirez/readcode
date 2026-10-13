import { describe, expect, it } from 'vitest';
import { blockItems, fileItems, fuzzyScore, mapLimit, rankItems, symbolItems, type SearchItem } from './search';
import type { Explain, Symbols, Tree } from './types';

const SHA = 'c'.repeat(40);

describe('fuzzyScore', () => {
  it('matches subsequences case-insensitively', () => {
    expect(fuzzyScore('bil', 'app/services/billing.py')).not.toBeNull();
    expect(fuzzyScore('BLPY', 'app/services/billing.py')).not.toBeNull();
  });
  it('rejects non-subsequences', () => {
    expect(fuzzyScore('xyz', 'app/main.py')).toBeNull();
    expect(fuzzyScore('yp', 'py')).toBeNull();
  });
  it('rewards contiguous and word-start matches', () => {
    expect(fuzzyScore('main', 'app/main.py')!).toBeGreaterThan(fuzzyScore('main', 'm_a_i_n.py')!);
    expect(fuzzyScore('ci', 'computeInvoice')!).toBeGreaterThan(fuzzyScore('ci', 'specific')!);
  });
  it('prefers shorter texts on equal matches', () => {
    expect(fuzzyScore('main', 'main.py')!).toBeGreaterThan(fuzzyScore('main', 'main_long_name.py')!);
  });
  it('finds the best alignment, not just the leftmost', () => {
    // leftmost "m" is inside "aamx", the better one starts "main"
    expect(fuzzyScore('main', 'xamx/main')!).toBeGreaterThan(fuzzyScore('main', 'xamxaxixn')!);
  });
  it('scores an empty query as 0', () => {
    expect(fuzzyScore('', 'anything')).toBe(0);
  });
});

const tree: Tree = {
  schemaVersion: 1,
  sha: SHA,
  files: [
    { path: 'app/main.py', blob: 'h', language: 'python', lines: 10, bytes: 1, indexed: true },
    { path: 'app/services/billing.py', blob: 'h', language: 'python', lines: 10, bytes: 1, indexed: true },
  ],
  excluded: [],
};

const symbols: Symbols = {
  schemaVersion: 1,
  sha: SHA,
  files: {
    'app/main.py': { defs: [{ name: 'main', kind: 'function', range: [4, 7] }], refs: [], imports: [] },
    'app/services/billing.py': {
      defs: [{ name: 'process', kind: 'function', range: [8, 10] }, { name: 'refund', kind: 'function', range: [13, 15] }],
      refs: [],
      imports: [],
    },
  },
};

const explain: Explain = {
  schemaVersion: 1,
  path: 'app/services/billing.py',
  blobHash: 'h',
  summary: '',
  blocks: [{ id: 'b1', range: [1, 3], title: 'Cálculo del total', body: '' }],
};

describe('index items', () => {
  it('builds file, symbol and block items with routes', () => {
    const f = fileItems(tree, 'fixture', SHA);
    expect(f[0]).toMatchObject({ kind: 'file', text: 'app/main.py', route: { kind: 'file', path: 'app/main.py' } });
    const s = symbolItems(symbols, 'fixture', SHA);
    expect(s.map((i) => i.text)).toEqual(['main', 'process', 'refund']);
    expect(s[2]).toMatchObject({ detail: 'function · app/services/billing.py:13', route: { path: 'app/services/billing.py', range: { start: 13, end: 15 } } });
    const b = blockItems(explain, 'fixture', SHA);
    expect(b[0]).toMatchObject({ kind: 'block', text: 'Cálculo del total', route: { range: { start: 1, end: 3 } } });
  });
});

describe('rankItems', () => {
  const items: SearchItem[] = [
    ...fileItems(tree, 'fixture', SHA),
    ...symbolItems(symbols, 'fixture', SHA),
    ...blockItems(explain, 'fixture', SHA),
  ];
  it('orders by score and drops non-matches', () => {
    const r = rankItems(items, 'refund');
    expect(r.map((i) => i.text)).toEqual(['refund']);
    expect(rankItems(items, 'main')[0].text).toBe('main');
  });
  it('limits the result count', () => {
    expect(rankItems(items, 'a', 2)).toHaveLength(2);
  });
  it('returns nothing for an empty query', () => {
    expect(rankItems(items, '  ')).toEqual([]);
  });
});

describe('mapLimit', () => {
  it('runs at most `limit` tasks at once and reports each result', async () => {
    let running = 0;
    let peak = 0;
    const seen: number[] = [];
    await mapLimit(
      Array.from({ length: 20 }, (_, i) => i),
      6,
      async (i) => {
        running++;
        peak = Math.max(peak, running);
        await new Promise((r) => setTimeout(r, 1 + (i % 3)));
        running--;
        return i * 2;
      },
      (r) => seen.push(r),
    );
    expect(peak).toBe(6);
    expect(seen.sort((a, b) => a - b)).toEqual(Array.from({ length: 20 }, (_, i) => i * 2));
  });
  it('keeps going when a task fails', async () => {
    const seen: number[] = [];
    await mapLimit([1, 2, 3], 2, async (i) => {
      if (i === 2) throw new Error('x');
      return i;
    }, (r) => seen.push(r));
    expect(seen.sort()).toEqual([1, 3]);
  });
  it('stops scheduling when cancelled', async () => {
    let calls = 0;
    let stop = false;
    await mapLimit([1, 2, 3, 4], 1, async () => {
      calls++;
      stop = true;
    }, undefined, () => stop);
    expect(calls).toBe(1);
  });
});
