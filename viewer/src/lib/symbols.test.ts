import { describe, expect, it } from 'vitest';
import { findUsages, refOffset, resolveName } from './symbols';
import type { Symbols } from './types';

const symbols: Symbols = {
  schemaVersion: 1,
  sha: 'a'.repeat(40),
  files: {
    'app/main.py': {
      defs: [{ name: 'main', kind: 'function', range: [4, 7] }],
      refs: [
        { name: 'process', line: 5, col: 16 },
        { name: 'main', line: 11, col: 4 },
        { name: 'helper', line: 6, col: 0 },
      ],
      imports: [
        { module: 'app.services.billing', line: 1, resolved: 'app/services/billing.py' },
        { module: 'app.services.auth', line: 1, resolved: 'app/services/auth.py' },
        { module: 'os', line: 2, resolved: null },
      ],
    },
    'app/services/auth.py': {
      defs: [{ name: 'process', kind: 'function', range: [5, 7] }],
      refs: [],
      imports: [],
    },
    'app/services/billing.py': {
      defs: [
        { name: 'process', kind: 'function', range: [8, 10] },
        { name: 'helper', kind: 'function', range: [1, 2] },
      ],
      refs: [{ name: 'helper', line: 9, col: 4 }],
      imports: [],
    },
    'app/models.py': {
      defs: [
        { name: 'Invoice', kind: 'class', range: [1, 7] },
        { name: 'describe', kind: 'method', range: [6, 7], parent: 'Invoice' },
      ],
      refs: [{ name: 'process', line: 3, col: 0 }],
      imports: [],
    },
    'z/other.py': {
      defs: [{ name: 'helper', kind: 'function', range: [3, 4] }],
      refs: [{ name: 'helper', line: 8, col: 2 }],
      imports: [],
    },
  },
};

describe('resolveName (same tiering as refs.py)', () => {
  it('resolves in the current file first', () => {
    const r = resolveName(symbols, 'app/main.py', 'main');
    expect(r.status).toBe('exact');
    expect(r.candidates.map((c) => [c.path, c.def.range])).toEqual([['app/main.py', [4, 7]]]);
  });

  it('then in imported files (ambiguous keeps all candidates of the tier)', () => {
    const r = resolveName(symbols, 'app/main.py', 'process');
    expect(r.status).toBe('ambiguous');
    expect(r.candidates.map((c) => c.path)).toEqual(['app/services/billing.py', 'app/services/auth.py']);
    expect(resolveName(symbols, 'app/main.py', 'helper').candidates.map((c) => c.path)).toEqual(['app/services/billing.py']);
  });

  it('then in the whole repo, sorted by path', () => {
    const r = resolveName(symbols, 'app/models.py', 'process');
    expect(r.status).toBe('ambiguous');
    expect(r.candidates.map((c) => c.path)).toEqual(['app/services/auth.py', 'app/services/billing.py']);
  });

  it('supports Class.method and reports broken names', () => {
    const r = resolveName(symbols, 'app/main.py', 'Invoice.describe');
    expect(r.status).toBe('exact');
    expect(r.candidates[0].def.range).toEqual([6, 7]);
    expect(resolveName(symbols, 'app/main.py', 'Other.describe').status).toBe('broken');
    expect(resolveName(symbols, 'app/main.py', 'nope')).toEqual({ status: 'broken', candidates: [] });
  });
});

describe('findUsages', () => {
  it('lists refs that resolve to the def, flagging ambiguous ones', () => {
    const def = symbols.files['app/services/auth.py'].defs[0];
    expect(findUsages(symbols, 'app/services/auth.py', def)).toEqual([
      { path: 'app/main.py', line: 5, col: 16, ambiguous: true },
      { path: 'app/models.py', line: 3, col: 0, ambiguous: true },
    ]);
  });

  it('excludes refs that resolve to another def of the same name', () => {
    const billingHelper = symbols.files['app/services/billing.py'].defs[1];
    expect(findUsages(symbols, 'app/services/billing.py', billingHelper)).toEqual([
      { path: 'app/main.py', line: 6, col: 0, ambiguous: false },
      { path: 'app/services/billing.py', line: 9, col: 4, ambiguous: false },
    ]);
    const otherHelper = symbols.files['z/other.py'].defs[0];
    expect(findUsages(symbols, 'z/other.py', otherHelper)).toEqual([{ path: 'z/other.py', line: 8, col: 2, ambiguous: false }]);
  });
});

describe('refOffset', () => {
  it('converts code-point columns to UTF-16 offsets', () => {
    expect(refOffset('x = process()', 4, 'process')).toBe(4);
    expect(refOffset('\u{1F600} = process()', 4, 'process')).toBe(5);
  });

  it('falls back to searching the name, null when absent', () => {
    expect(refOffset('  process()', 7, 'process')).toBe(2);
    expect(refOffset('nothing here', 0, 'process')).toBeNull();
  });
});
