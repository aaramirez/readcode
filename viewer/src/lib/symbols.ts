// Symbol navigation over symbols.json: name resolution with the same tiering
// as core/readcode/refs.py `resolve` (current file -> imported files -> whole
// repo; the first tier with matches decides) and "find usages" of a definition.

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

/** Resolve a bare name seen in `currentPath` to its definition(s). */
export function resolveName(symbols: Symbols, currentPath: string, name: string): NameResolution {
  const imported = (symbols.files[currentPath]?.imports ?? [])
    .map((i) => i.resolved)
    .filter((p): p is string => !!p);
  const tiers = [[currentPath], [...new Set(imported)], Object.keys(symbols.files).sort()];
  for (let t = 0; t < tiers.length; t++) {
    const found = candidates(symbols, tiers[t], name);
    if (t === 2) found.sort((a, b) => (a.path < b.path ? -1 : a.path > b.path ? 1 : cmpRange(a.def.range, b.def.range)));
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
  if (lineText.startsWith(name, off)) return off;
  const found = lineText.indexOf(name);
  return found < 0 ? null : found;
}
