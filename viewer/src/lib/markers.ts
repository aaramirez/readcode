// Marker parser: a TypeScript port of core/readcode/refs.py `parse_markers`.
//
// The grammar is documented in the refs.py module docstring and MUST stay
// identical; schemas/marker-vectors.json is checked by both pytest
// (core/tests/test_marker_vectors.py) and vitest (markers.test.ts).
//
// Python-isms reproduced on purpose so both sides agree on every input:
// - lines are split like str.splitlines(keepends=True) (also on \v, \f,
//   \x1c-\x1e, \x85, U+2028, U+2029), which matters for fence detection;
// - a closing fence may be followed only by str.isspace() characters.
// Offsets are not part of the contract (Python counts code points, JS UTF-16).

export type ParsedMarkerKind = 'symbol' | 'lines' | 'archify' | 'invalid';

export interface ParsedMarker {
  kind: ParsedMarkerKind;
  /** Exact marker text, e.g. "[[ref:app/x.py#f|label]]". */
  raw: string;
  /** null = current file (or not applicable). */
  path: string | null;
  /** Symbol for "symbol" markers; diagram name for "archify" markers. */
  symbol: string | null;
  range: [number, number] | null;
  label: string | null;
}

const WS = ' \\t\\n\\r\\f\\v'; // regex class body: ASCII whitespace only
const MARKER_RE = /\[\[(ref|archify):([^\]\n]*)\]\]/g;
const LINES_RE = new RegExp(`^([^${WS}#:|\\[\\]]*):L([0-9]+)(?:-([0-9]+))?$`);
const SYMBOL_RE = new RegExp(`^([^${WS}#:|\\[\\]]*)#([^${WS}|\\[\\]#]+)$`);
const ARCHIFY_RE = new RegExp(`^[^${WS}|\\[\\]:]+$`);
const FENCE_RE = /^( {0,3})(`{3,}|~{3,})/;
const BACKTICKS_RE = /`+/g;
const PARA_SEP_RE = /\n[ \t]*\n/g;
// str.splitlines() boundaries.
const LINE_RE = /[^\n\r\v\f\x1c\x1d\x1e\x85\u2028\u2029]*(?:\r\n|[\n\r\v\f\x1c\x1d\x1e\x85\u2028\u2029])?/g;
// str.isspace() characters.
const PY_SPACE_ONLY = /^[\t\n\v\f\r\x1c-\x1f \x85\xa0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]*$/;

function blank(text: string): string {
  return text.replace(/[^\n]/g, ' ');
}

function splitLines(text: string): string[] {
  const out: string[] = [];
  for (const m of text.matchAll(LINE_RE)) {
    if (m[0] === '') break; // the regex matches the empty string at the end
    out.push(m[0]);
  }
  return out;
}

/** Blank inline code spans within one paragraph. */
function maskInline(para: string): string {
  const runs = [...para.matchAll(BACKTICKS_RE)].map((m) => [m.index, m.index + m[0].length] as const);
  const out: string[] = [];
  let last = 0;
  let i = 0;
  while (i < runs.length) {
    const n = runs[i][1] - runs[i][0];
    let j = -1;
    for (let k = i + 1; k < runs.length; k++) {
      if (runs[k][1] - runs[k][0] === n) {
        j = k;
        break;
      }
    }
    if (j < 0) {
      i += 1;
      continue;
    }
    out.push(para.slice(last, runs[i][0]));
    out.push(blank(para.slice(runs[i][0], runs[j][1])));
    last = runs[j][1];
    i = j + 1;
  }
  out.push(para.slice(last));
  return out.join('');
}

/** Replace fenced blocks and inline code by spaces (same length). */
function maskCode(text: string): string {
  const out: string[] = [];
  let fence: { ch: string; len: number } | null = null;
  for (const line of splitLines(text)) {
    const m = FENCE_RE.exec(line);
    if (fence === null) {
      if (m) {
        fence = { ch: m[2][0], len: m[2].length };
        out.push(blank(line));
      } else out.push(line);
    } else {
      out.push(blank(line));
      if (m && m[2][0] === fence.ch && m[2].length >= fence.len && PY_SPACE_ONLY.test(line.slice(m[0].length))) {
        fence = null;
      }
    }
  }
  const masked = out.join('');
  const parts: string[] = [];
  let pos = 0;
  for (const sep of masked.matchAll(PARA_SEP_RE)) {
    parts.push(maskInline(masked.slice(pos, sep.index)));
    parts.push(sep[0]);
    pos = sep.index + sep[0].length;
  }
  parts.push(maskInline(masked.slice(pos)));
  return parts.join('');
}

/** Parse the body of one marker ("ref" | "archify", text between ":" and "]]"). */
export function parseMarkerBody(kindWord: 'ref' | 'archify', body: string, raw: string): ParsedMarker {
  const invalid: ParsedMarker = { kind: 'invalid', raw, path: null, symbol: null, range: null, label: null };
  if (kindWord === 'archify') {
    return ARCHIFY_RE.test(body) ? { ...invalid, kind: 'archify', symbol: body } : invalid;
  }
  const bar = body.indexOf('|');
  const target = bar < 0 ? body : body.slice(0, bar);
  const label = bar < 0 ? null : body.slice(bar + 1);
  if (label === '') return invalid;
  let m = LINES_RE.exec(target);
  if (m) {
    const start = parseInt(m[2], 10);
    const end = m[3] !== undefined ? parseInt(m[3], 10) : start;
    return { kind: 'lines', raw, path: m[1] || null, symbol: null, range: [start, end], label };
  }
  m = SYMBOL_RE.exec(target);
  if (m) return { kind: 'symbol', raw, path: m[1] || null, symbol: m[2], range: null, label };
  return invalid;
}

/** All markers of a Markdown source, outside fenced blocks and inline code. */
export function parseMarkers(markdown: string): ParsedMarker[] {
  const masked = maskCode(markdown);
  const markers: ParsedMarker[] = [];
  for (const m of masked.matchAll(MARKER_RE)) {
    const raw = markdown.slice(m.index, m.index + m[0].length);
    markers.push(parseMarkerBody(m[1] as 'ref' | 'archify', m[2], raw));
  }
  return markers;
}

/** Marker at the start of `src.slice(pos)` (for markdown-it); null if none. */
export function markerAt(src: string, pos: number): { marker: ParsedMarker; end: number } | null {
  const re = /\[\[(ref|archify):([^\]\n]*)\]\]/y;
  re.lastIndex = pos;
  const m = re.exec(src);
  if (!m) return null;
  return { marker: parseMarkerBody(m[1] as 'ref' | 'archify', m[2], m[0]), end: pos + m[0].length };
}
