// Symbol navigation over symbols.json: name resolution with the same tiering
// as core/readcode/refs.py `resolve` and "find usages" of a definition.
// Tiers (the first one with matches decides):
//   non-Go: current file -> imported files -> whole repo
//   Go:     current file -> same package (other .go files directly in its folder)
//           -> .go files directly in each import's `resolvedDir` -> whole repo
//           (`_test.go` files only count in the package tiers when the current
//           file is itself a test).

import type { Range, SymbolDef, Symbols } from './types';

export interface DefLocation {
  path: string;
  def: SymbolDef;
}

export interface NameResolution {
  status: 'exact' | 'ambiguous' | 'broken';
  /** One entry when exact, several when ambiguous, none when broken. */
  candidates: DefLocation[];
}

/** Defs of a file matching `symbol` ("Class.method" matches a def `method` whose parent is `Class`). */
function matches(defs: SymbolDef[], symbol: string): SymbolDef[] {
  const dot = symbol.lastIndexOf('.');
  const tail = symbol.slice(dot + 1);
  const parentPath = dot < 0 ? '' : symbol.slice(0, dot);
  const parent = parentPath.slice(parentPath.lastIndexOf('.') + 1);
  return defs.filter((d) => d.name === symbol || (dot >= 0 && d.name === tail && d.parent === parent));
}

function candidates(symbols: Symbols, paths: string[], symbol: string): DefLocation[] {
  const out: DefLocation[] = [];
  for (const p of paths) {
    for (const def of matches(symbols.files[p]?.defs ?? [], symbol)) out.push({ path: p, def });
  }
  return out;
}

function cmpRange(a: Range, b: Range): number {
  return a[0] - b[0] || a[1] - b[1];
}

const goIndexCache = new WeakMap<Symbols, Map<string, string[]>>();

/** `{directory: sorted .go files directly in it}` ("" = repo root), built once per symbols object. */
function goPackageIndex(symbols: Symbols): Map<string, string[]> {
  let index = goIndexCache.get(symbols);
  if (!index) {
    index = new Map();
    for (const p of Object.keys(symbols.files).sort()) {
      const slash = p.lastIndexOf('/');
      if (!p.slice(slash + 1).endsWith('.go')) continue;
      const dir = p.slice(0, Math.max(slash, 0));
      const list = index.get(dir);
      if (list) list.push(p);
      else index.set(dir, [p]);
    }
    goIndexCache.set(symbols, index);
  }
  return index;
}

function goPackageFiles(index: Map<string, string[]>, dir: string, includeTests: boolean): string[] {
  return (index.get(dir) ?? []).filter((p) => includeTests || !p.endsWith('_test.go'));
}

function resolutionTiers(symbols: Symbols, currentPath: string): string[][] {
  const imports = symbols.files[currentPath]?.imports ?? [];
  const all = Object.keys(symbols.files).sort();
  if (!currentPath.endsWith('.go')) {
    const imported = imports.map((i) => i.resolved).filter((p): p is string => !!p);
    return [[currentPath], [...new Set(imported)], all];
  }
  const index = goPackageIndex(symbols);
  const tests = currentPath.endsWith('_test.go');
  const same = goPackageFiles(index, currentPath.slice(0, Math.max(currentPath.lastIndexOf('/'), 0)), tests).filter(
    (p) => p !== currentPath,
  );
  const imported: string[] = [];
  for (const i of imports) {
    if (i.resolvedDir !== undefined) imported.push(...goPackageFiles(index, i.resolvedDir.replace(/^\/+|\/+$/g, ''), tests));
  }
  return [[currentPath], same, [...new Set(imported)], all];
}

/** Resolve a bare name seen in `currentPath` to its definition(s). */
export function resolveName(symbols: Symbols, currentPath: string, name: string): NameResolution {
  const tiers = resolutionTiers(symbols, currentPath);
  for (let t = 0; t < tiers.length; t++) {
    const found = candidates(symbols, tiers[t], name);
    if (t === tiers.length - 1) found.sort((a, b) => (a.path < b.path ? -1 : a.path > b.path ? 1 : cmpRange(a.def.range, b.def.range)));
    if (found.length === 1) return { status: 'exact', candidates: found };
    if (found.length > 1) return { status: 'ambiguous', candidates: found };
  }
  return { status: 'broken', candidates: [] };
}

export interface Usage {
  path: string;
  line: number;
  col: number;
  /** True when the reference also resolves to other definitions. */
  ambiguous: boolean;
}

function sameDef(a: DefLocation, path: string, def: SymbolDef): boolean {
  return a.path === path && a.def.name === def.name && a.def.range[0] === def.range[0] && a.def.range[1] === def.range[1];
}

/** References across the repo whose name resolves (alone or among others) to `def` in `path`. */
export function findUsages(symbols: Symbols, path: string, def: SymbolDef): Usage[] {
  const out: Usage[] = [];
  for (const p of Object.keys(symbols.files).sort()) {
    const refs = symbols.files[p].refs.filter((r) => r.name === def.name);
    if (refs.length === 0) continue;
    const res = resolveName(symbols, p, def.name);
    if (!res.candidates.some((c) => sameDef(c, path, def))) continue;
    for (const r of refs) {
      out.push({ path: p, line: r.line, col: r.col, ambiguous: res.status === 'ambiguous' });
    }
  }
  return out.sort((a, b) => (a.path < b.path ? -1 : a.path > b.path ? 1 : a.line - b.line || a.col - b.col));
}

/**
 * UTF-16 offset in `lineText` of a symbols.json column (0-based, counted in
 * code points). Falls back to searching the name when the column does not
 * point at it; null if the name is not on the line.
 */
export function refOffset(lineText: string, col: number, name: string): number | null {
  let off = 0;
  for (let cp = 0; cp < col && off < lineText.length; cp++) {
    const c = lineText.codePointAt(off)!;
    off += c > 0xffff ? 2 : 1;
  }
  if (lineText.startsWith(name, off) && isWholeWord(lineText, off, name.length)) return off;
  // Fallback: the whole-word occurrence nearest to the declared column.
  let best: number | null = null;
  for (let i = lineText.indexOf(name); i >= 0; i = lineText.indexOf(name, i + 1)) {
    if (isWholeWord(lineText, i, name.length) && (best === null || Math.abs(i - off) < Math.abs(best - off))) best = i;
  }
  return best;
}

const IDENT_CHAR = /[\p{L}\p{N}_$]/u;

function isWholeWord(text: string, at: number, len: number): boolean {
  const before = at > 0 ? String.fromCodePoint(text.codePointAt(at - 1)!) : '';
  const after = at + len < text.length ? String.fromCodePoint(text.codePointAt(at + len)!) : '';
  return !IDENT_CHAR.test(before) && !IDENT_CHAR.test(after);
}
