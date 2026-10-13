// Hash router of the viewer.
//
// Grammar (every <segment> is URL-encoded with encodeURIComponent; a <path> is a
// repo path whose "/"-separated segments are each encoded):
//
//   #/                                        → study list (catalog)
//   #/<study>                                 → overview of the latest snapshot
//   #/<study>/<sha7+>/                        → overview of that snapshot
//   #/<study>/<sha>/f/<path>[:L<a>[-<b>]]     → file, optional line range (1-based)
//   #/<study>/<sha>/d/<path>                  → directory summary ("d/" = repo root)
//   #/<study>/<sha>/tour/<id>[/<step>]        → tour step (1-based)
//   #/<study>/<sha>/graph[/<path>]            → graph tab, optionally focused on a file
//   #/<study>/<sha>/diagrams[/<name>]         → diagrams tab, optionally one diagram
//   #/<study>/diff/<shaA>..<shaB>[/<path>]    → diff view, optionally one file
//
// <sha> may be any unique prefix of at least 7 hex chars; resolveSha() expands it
// against study.snapshots. The ":L" suffix is unambiguous because ":" inside a
// path is always encoded (%3A).
//
// Navigation goes through location.hash, so the browser history is the
// navigation history; the UI ← → buttons call history.back()/forward().

import type { Snapshot, Study } from './types';

export interface LineRange {
  start: number;
  end?: number;
}

export type Route =
  | { kind: 'catalog' }
  | { kind: 'study'; study: string }
  | { kind: 'overview'; study: string; sha: string }
  | { kind: 'file'; study: string; sha: string; path: string; range?: LineRange }
  | { kind: 'dir'; study: string; sha: string; path: string }
  | { kind: 'tour'; study: string; sha: string; id: string; step?: number }
  | { kind: 'graph'; study: string; sha: string; path?: string }
  | { kind: 'diagrams'; study: string; sha: string; name?: string }
  | { kind: 'diff'; study: string; a: string; b: string; path?: string }
  | { kind: 'notfound'; hash: string };

const SHA = /^[0-9a-f]{7,40}$/;
const POSITIVE = /^[1-9][0-9]*$/;
const LINES_SUFFIX = /:L([1-9][0-9]*)(?:-([1-9][0-9]*))?$/;

function enc(s: string): string {
  return encodeURIComponent(s);
}

function encPath(path: string): string {
  return path.split('/').map(enc).join('/');
}

/** Decode a list of encoded segments into a repo path; null if malformed. */
function decPath(segments: string[]): string | null {
  try {
    const parts = segments.map(decodeURIComponent);
    if (parts.some((p) => p === '')) return null;
    return parts.join('/');
  } catch {
    return null;
  }
}

function dec(s: string): string | null {
  try {
    return decodeURIComponent(s);
  } catch {
    return null;
  }
}

export function parse(hash: string): Route {
  const notFound: Route = { kind: 'notfound', hash };
  let h = hash.startsWith('#') ? hash.slice(1) : hash;
  if (h === '' || h === '/') return { kind: 'catalog' };
  if (!h.startsWith('/')) return notFound;
  h = h.slice(1);

  const segs = h.split('/');
  const study = dec(segs[0]);
  if (!study) return notFound;
  if (segs.length === 1) return { kind: 'study', study };

  // diff/<a>..<b>[/<path>]
  if (segs[1] === 'diff') {
    const m = /^([0-9a-f]{7,40})\.\.([0-9a-f]{7,40})$/.exec(segs[2] ?? '');
    if (!m) return notFound;
    const rest = segs.slice(3);
    if (rest.length === 0 || (rest.length === 1 && rest[0] === '')) {
      return { kind: 'diff', study, a: m[1], b: m[2] };
    }
    const path = decPath(rest);
    return path === null ? notFound : { kind: 'diff', study, a: m[1], b: m[2], path };
  }

  const sha = segs[1];
  if (!SHA.test(sha)) return notFound;
  const rest = segs.slice(2);
  if (rest.length === 0 || (rest.length === 1 && rest[0] === '')) {
    return { kind: 'overview', study, sha };
  }

  const [section, ...tail] = rest;
  switch (section) {
    case 'f': {
      if (tail.length === 0) return notFound;
      let range: LineRange | undefined;
      const last = tail[tail.length - 1];
      const lm = LINES_SUFFIX.exec(last);
      if (lm) {
        tail[tail.length - 1] = last.slice(0, lm.index);
        range = { start: Number(lm[1]) };
        if (lm[2] !== undefined) range.end = Number(lm[2]);
      }
      const path = decPath(tail);
      if (path === null) return notFound;
      return range ? { kind: 'file', study, sha, path, range } : { kind: 'file', study, sha, path };
    }
    case 'd': {
      if (tail.length === 0 || (tail.length === 1 && tail[0] === '')) {
        return { kind: 'dir', study, sha, path: '' };
      }
      const path = decPath(tail);
      return path === null ? notFound : { kind: 'dir', study, sha, path };
    }
    case 'tour': {
      if (tail.length < 1 || tail.length > 2 || tail[0] === '') return notFound;
      const id = dec(tail[0]);
      if (id === null) return notFound;
      if (tail.length === 1) return { kind: 'tour', study, sha, id };
      if (!POSITIVE.test(tail[1])) return notFound;
      return { kind: 'tour', study, sha, id, step: Number(tail[1]) };
    }
    case 'graph': {
      if (tail.length === 0) return { kind: 'graph', study, sha };
      const path = decPath(tail);
      return path === null ? notFound : { kind: 'graph', study, sha, path };
    }
    case 'diagrams': {
      if (tail.length === 0) return { kind: 'diagrams', study, sha };
      if (tail.length !== 1) return notFound;
      const name = dec(tail[0]);
      return name ? { kind: 'diagrams', study, sha, name } : notFound;
    }
    default:
      return notFound;
  }
}

export function format(route: Route): string {
  switch (route.kind) {
    case 'catalog':
      return '#/';
    case 'notfound':
      return route.hash.startsWith('#') ? route.hash : '#' + route.hash;
    case 'study':
      return `#/${enc(route.study)}`;
    case 'diff':
      return (
        `#/${enc(route.study)}/diff/${route.a}..${route.b}` +
        (route.path ? '/' + encPath(route.path) : '')
      );
  }
  const base = `#/${enc(route.study)}/${route.sha}/`;
  switch (route.kind) {
    case 'overview':
      return base;
    case 'file': {
      let s = `${base}f/${encPath(route.path)}`;
      if (route.range) {
        s += `:L${route.range.start}`;
        if (route.range.end !== undefined) s += `-${route.range.end}`;
      }
      return s;
    }
    case 'dir':
      return `${base}d/${route.path === '' ? '' : encPath(route.path)}`;
    case 'tour':
      return `${base}tour/${enc(route.id)}` + (route.step !== undefined ? `/${route.step}` : '');
    case 'graph':
      return `${base}graph` + (route.path ? '/' + encPath(route.path) : '');
    case 'diagrams':
      return `${base}diagrams` + (route.name ? '/' + enc(route.name) : '');
  }
}

/** Expand a sha prefix against the study's snapshots; null if unknown or ambiguous. */
export function resolveSha(study: Study, prefix: string): string | null {
  const matches = study.snapshots.filter((s) => s.sha.startsWith(prefix));
  return matches.length === 1 ? matches[0].sha : null;
}

/** Most recent snapshot by commit date (ties: the later one in the list). */
export function latestSnapshot(study: Study): Snapshot | null {
  let best: Snapshot | null = null;
  for (const s of study.snapshots) {
    if (!best || Date.parse(s.date) >= Date.parse(best.date)) best = s;
  }
  return best;
}

/** Study name of a route, if any. */
export function routeStudy(route: Route): string | null {
  return route.kind === 'catalog' || route.kind === 'notfound' ? null : route.study;
}

/** Snapshot sha (possibly a prefix) of a route, if it is bound to one. */
export function routeSha(route: Route): string | null {
  switch (route.kind) {
    case 'overview':
    case 'file':
    case 'dir':
    case 'tour':
    case 'graph':
    case 'diagrams':
      return route.sha;
    case 'diff':
      return route.b;
    default:
      return null;
  }
}

export function navigate(route: Route): void {
  const hash = format(route);
  if (location.hash !== hash) location.hash = hash;
}

export function currentRoute(): Route {
  return parse(location.hash);
}
