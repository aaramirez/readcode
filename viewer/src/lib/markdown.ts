// Shared Markdown renderer for every markdown-bearing doc of a study (file and
// block explanations, dir summaries, overview, tours, diff explanations).
//
// markdown-it runs with html: false, so raw HTML in the source is escaped; the
// marker plugin below only emits fixed tags whose attributes are escaped.
//
// Markers (grammar: lib/markers.ts, mirror of core/readcode/refs.py):
//   [[ref:...]]      -> resolution looked up in links.json (docs[docKey], by raw text):
//                       exact     -> <a class="rc-ref" href="#/<study>/<sha>/f/<target>:L<a>-<b>">
//                       ambiguous -> <button class="rc-ref rc-ambiguous" data-candidates="[{label, href}]">
//                       otherwise -> <span class="rc-ref rc-broken" title="referencia rota">
//   [[archify:name]] -> sandboxed, lazy iframe + "abrir en pestaña" link
//                       only when links.json resolves it as exact; otherwise an error note
//   ```mermaid       -> <div class="rc-mermaid"><pre class="rc-mermaid-src">source</pre></div>,
//                       rendered later by lib/mermaid.ts (the <pre> is the fallback).

import MarkdownIt, { type Env as MdEnv, type StateInline, type Token } from 'markdown-it';
import { isDiagramName, markerAt, type ParsedMarker } from './markers';
import { format } from './router';
import type { LinkMarker, Links } from './types';

export interface MarkdownContext {
  study: string;
  /** Snapshot that ref targets and diagrams belong to. */
  sha: string;
  /** links.json of that snapshot (or diff); null when missing. */
  links: Links | null;
  /** Key of the doc in links.json, e.g. "explain/app/main.py.json", "overview.md". */
  docKey: string;
  /** URL of diagrams/<name>.html; null for an unsafe name. */
  diagramUrl: (name: string) => string | null;
  /** Snapshot a ref target opens in (default: sha). Diffs open targets missing from B in A. */
  shaFor?: (target: string) => string;
}

export interface Candidate {
  label: string;
  href: string;
}

interface Env extends MdEnv {
  ctx?: MarkdownContext;
  byRaw?: Map<string, LinkMarker>;
}

const md = new MarkdownIt({ html: false, linkify: true });
const esc = md.utils.escapeHtml;

function markerRule(state: StateInline, silent: boolean): boolean {
  if (state.src.charCodeAt(state.pos) !== 0x5b /* [ */) return false;
  const hit = markerAt(state.src, state.pos);
  if (!hit) return false;
  if (!silent) {
    const token = state.push('rc_marker', '', 0);
    token.meta = { marker: hit.marker };
  }
  state.pos = hit.end;
  return true;
}

md.inline.ruler.before('link', 'rc_marker', markerRule);

function fileHref(ctx: MarkdownContext, target: string, range: [number, number]): string {
  const sha = ctx.shaFor?.(target) ?? ctx.sha;
  return format({ kind: 'file', study: ctx.study, sha, path: target, range: { start: range[0], end: range[1] === range[0] ? undefined : range[1] } });
}

function refText(m: ParsedMarker): string {
  if (m.label !== null) return m.label;
  if (m.kind === 'symbol') return m.symbol ?? m.raw;
  if (m.kind === 'lines' && m.range) {
    const lines = m.range[0] === m.range[1] ? `L${m.range[0]}` : `L${m.range[0]}-${m.range[1]}`;
    return m.path ? `${m.path}:${lines}` : lines;
  }
  return m.raw;
}

function rangeLabel(target: string, range: [number, number]): string {
  return range[0] === range[1] ? `${target}:L${range[0]}` : `${target}:L${range[0]}-${range[1]}`;
}

function broken(text: string, cls = 'rc-ref', title = 'referencia rota'): string {
  return `<span class="${cls} rc-broken" title="${esc(title)}">${esc(text)}</span>`;
}

function renderMarker(m: ParsedMarker, env: Env): string {
  const ctx = env.ctx;
  const entry = env.byRaw?.get(m.raw);
  if (m.kind === 'invalid') return broken(m.raw, 'rc-ref', 'marcador inválido');
  if (m.kind === 'archify') {
    const name = m.symbol ?? '';
    // Embed only diagrams links.json resolved (exact) and whose name is safe.
    const rawUrl = ctx && entry?.status === 'exact' && isDiagramName(name) ? ctx.diagramUrl(name) : null;
    if (rawUrl === null) {
      return `<span class="rc-archify rc-archify-broken">Diagrama no encontrado: <code>${esc(name)}</code></span>`;
    }
    const url = esc(rawUrl);
    return (
      `<span class="rc-archify">` +
      `<iframe sandbox="allow-scripts" loading="lazy" src="${url}" title="Diagrama ${esc(name)}"></iframe>` +
      `<a class="rc-archify-open" href="${url}" target="_blank" rel="noopener">abrir en pestaña</a>` +
      `</span>`
    );
  }
  const text = refText(m);
  const cls = m.label === null ? 'rc-ref rc-code' : 'rc-ref';
  if (ctx && entry?.status === 'exact' && entry.target && entry.range) {
    const href = fileHref(ctx, entry.target, entry.range);
    return `<a class="${cls}" href="${esc(href)}" title="${esc(rangeLabel(entry.target, entry.range))}">${esc(text)}</a>`;
  }
  if (ctx && entry?.status === 'ambiguous' && entry.candidates?.length) {
    const candidates: Candidate[] = entry.candidates.map((c) => ({
      label: rangeLabel(c.target, c.range),
      href: fileHref(ctx, c.target, c.range),
    }));
    return (
      `<button type="button" class="${cls} rc-ambiguous" data-candidates="${esc(JSON.stringify(candidates))}" ` +
      `title="Referencia ambigua: ${candidates.length} candidatos">${esc(text)}</button>`
    );
  }
  return broken(text, cls);
}

md.renderer.rules.rc_marker = (tokens: Token[], idx: number, _opts, env?: MdEnv) =>
  renderMarker((tokens[idx].meta as { marker: ParsedMarker }).marker, (env ?? {}) as Env);

const defaultFence = md.renderer.rules.fence!;
md.renderer.rules.fence = (tokens, idx, opts, env, self) => {
  const token = tokens[idx];
  if (token.info.trim().split(/\s+/)[0] === 'mermaid') {
    return `<div class="rc-mermaid"><pre class="rc-mermaid-src">${esc(token.content)}</pre></div>\n`;
  }
  return defaultFence(tokens, idx, opts, env, self);
};

/** Render Markdown; with a context, markers are resolved against links.json. */
export function renderMarkdown(src: string, ctx?: MarkdownContext): string {
  const env: Env = {};
  if (ctx) {
    env.ctx = ctx;
    env.byRaw = new Map((ctx.links?.docs[ctx.docKey] ?? []).map((m) => [m.raw, m]));
  }
  return md.render(src, env);
}

/** Candidates of an ambiguous ref element rendered by renderMarkdown. */
export function readCandidates(el: Element): Candidate[] {
  try {
    const parsed = JSON.parse(el.getAttribute('data-candidates') ?? '[]') as Candidate[];
    return parsed.filter((c) => typeof c.label === 'string' && typeof c.href === 'string' && c.href.startsWith('#/'));
  } catch {
    return [];
  }
}
