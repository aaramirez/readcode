import { describe, expect, it } from 'vitest';
import { findUsages, refOffset, resolveName } from './symbols';
import type { FileSymbols, Range, SymbolImport, Symbols } from './types';

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

describe('resolveName Go tiers (mirrors core test_refs.py)', () => {
  const f = (names: string[], imports: SymbolImport[] = []): FileSymbols => ({
    defs: names.map((name) => ({ name, kind: 'function' as const, range: [1, 2] as Range })),
    refs: [],
    imports,
  });
  const goSyms = (files: Record<string, FileSymbols>): Symbols => ({ schemaVersion: 1, sha: 'b'.repeat(40), files });
  const paths = (r: { candidates: { path: string }[] }) => r.candidates.map((c) => c.path).sort();
  const GO = goSyms({
    'internal/app/a.go': f(['Run'], [{ module: 'x/internal/util', line: 3, resolved: null, resolvedDir: 'internal/util' }]),
    'internal/app/b.go': f(['Foo']),
    'internal/app/b_test.go': f(['TestHelper', 'OnlyInTest']),
    'internal/app/c_test.go': f(['Use']),
    'internal/app/sub/s.go': f(['InSub']),
    'internal/util/u.go': f(['Bar', 'Foo2']),
    'internal/util/u_test.go': f(['UtilTest']),
    'other/o.go': f(['Foo', 'Bar', 'InSub', 'OnlyInTest', 'UtilTest']),
  });

  it('same package beats another package', () => {
    const r = resolveName(GO, 'internal/app/a.go', 'Foo');
    expect(r.status).toBe('exact');
    expect(r.candidates[0].path).toBe('internal/app/b.go');
  });

  it('imported package beats the repo', () => {
    const r = resolveName(GO, 'internal/app/a.go', 'Bar');
    expect(r.status).toBe('exact');
    expect(r.candidates[0].path).toBe('internal/util/u.go');
  });

  it('a subfolder is not the same package', () => {
    const r = resolveName(GO, 'internal/app/a.go', 'InSub');
    expect(r.status).toBe('ambiguous');
    expect(paths(r)).toEqual(['internal/app/sub/s.go', 'other/o.go']);
  });

  it('skips _test.go in package tiers for a non-test file (falls to the repo tier)', () => {
    expect(paths(resolveName(GO, 'internal/app/a.go', 'OnlyInTest'))).toEqual(['internal/app/b_test.go', 'other/o.go']);
    expect(paths(resolveName(GO, 'internal/app/a.go', 'UtilTest'))).toEqual(['internal/util/u_test.go', 'other/o.go']);
  });

  it('includes _test.go for a test file', () => {
    const r = resolveName(GO, 'internal/app/c_test.go', 'OnlyInTest');
    expect(r.status).toBe('exact');
    expect(r.candidates[0].path).toBe('internal/app/b_test.go');
    const imp: SymbolImport = { module: 'm', line: 1, resolved: null, resolvedDir: 'internal/util' };
    const syms = goSyms({ ...GO.files, 'internal/app/c_test.go': f(['Use'], [imp]) });
    const u = resolveName(syms, 'internal/app/c_test.go', 'UtilTest');
    expect(u.status).toBe('exact');
    expect(u.candidates[0].path).toBe('internal/util/u_test.go');
  });

  it('falls back to the repo and reports broken', () => {
    expect(resolveName(GO, 'other/o.go', 'Foo2').candidates[0].path).toBe('internal/util/u.go');
    expect(resolveName(GO, 'other/o.go', 'Nope').status).toBe('broken');
  });

  it('root package files (current dir "") count as the same package', () => {
    const syms = goSyms({ 'main.go': f(['Main']), 'x.go': f(['Helper']), 'd/y.go': f(['Helper']) });
    const r = resolveName(syms, 'main.go', 'Helper');
    expect(r.status).toBe('exact');
    expect(r.candidates[0].path).toBe('x.go');
  });

  it('resolvedDir "" is the repo root (not falsy)', () => {
    const syms = goSyms({
      'cmd/m.go': f(['Run'], [{ module: 'x', line: 1, resolved: null, resolvedDir: '' }]),
      'root.go': f(['RootFn']),
      'root_test.go': f(['RootTest']),
      'pkg/p.go': f(['RootFn', 'RootTest']),
    });
    const r = resolveName(syms, 'cmd/m.go', 'RootFn');
    expect(r.status).toBe('exact');
    expect(r.candidates[0].path).toBe('root.go');
    expect(paths(resolveName(syms, 'cmd/m.go', 'RootTest'))).toEqual(['pkg/p.go', 'root_test.go']);
  });

  it('non-Go files ignore resolvedDir and the same-directory tier', () => {
    const syms = goSyms({
      'pkg/a.java': f(['Foo'], [{ module: 'm', line: 1, resolved: 'lib/B.java' }]),
      'pkg/c.java': f(['Same']),
      'lib/B.java': f(['Bee']),
      'z/Same.java': f(['Same']),
    });
    expect(resolveName(syms, 'pkg/a.java', 'Bee').candidates[0].path).toBe('lib/B.java');
    expect(resolveName(syms, 'pkg/a.java', 'Same').status).toBe('ambiguous');
  });

  it('findUsages goes through the Go tiers', () => {
    const def = GO.files['internal/app/b.go'].defs[0];
    const syms = goSyms({
      ...GO.files,
      'internal/app/a.go': { ...GO.files['internal/app/a.go'], refs: [{ name: 'Foo', line: 5, col: 1 }] },
      'other/o.go': { ...GO.files['other/o.go'], refs: [{ name: 'Foo', line: 2, col: 0 }] },
    });
    // a.go's Foo resolves to b.go (same package); o.go's own Foo wins in its tier.
    expect(findUsages(syms, 'internal/app/b.go', def)).toEqual([{ path: 'internal/app/a.go', line: 5, col: 1, ambiguous: false }]);
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

  it('only accepts whole-word matches, nearest to the column', () => {
    expect(refOffset('reprocess(); process()', 99, 'process')).toBe(13);
    expect(refOffset('reprocess(); process()', 0, 'process')).toBe(13);
    expect(refOffset('processor()', 0, 'process')).toBeNull();
    expect(refOffset('process(process)', 9, 'process')).toBe(8);
    expect(refOffset('process(process)', 7, 'process')).toBe(8);
    expect(refOffset('$process + process_x', 0, 'process')).toBeNull();
  });
});
