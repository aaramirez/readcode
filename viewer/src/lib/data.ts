// Typed fetch client for a readcode kb (see schemas/ and spec §4).
//
// Every request is cached in memory as a promise (one network request per URL).
// HTTP 404 resolves to null; any other failure throws (and is evicted from the
// cache so a later call can retry).

import { isDiagramName } from './markers';
import type {
  Catalog,
  Changes,
  DiffFileExplain,
  DiagramEntry,
  DirSummary,
  Explain,
  Graph,
  Issues,
  Links,
  Study,
  Symbols,
  Tour,
  TourListEntry,
  Tree,
} from './types';

export type FetchFn = (input: string) => Promise<Response>;

export class HttpError extends Error {
  constructor(
    readonly url: string,
    readonly status: number,
  ) {
    super(`HTTP ${status} al cargar ${url}`);
    this.name = 'HttpError';
  }
}

/** URL-encode each segment of a slash-separated repo path. */
export function encodePath(path: string): string {
  return path.split('/').map(encodeURIComponent).join('/');
}

const TOUR_KEY = /^tours\/(.+)\.json$/;
const ARCHIFY_RAW = /^\[\[archify:(.+)\]\]$/;

export class KbClient {
  private cache = new Map<string, Promise<unknown>>();

  /** `base` is the kb URL prefix, ending with "/" (the server mounts the kb at /kb/). */
  constructor(
    private readonly base: string = 'kb/',
    private readonly fetchFn: FetchFn = (input) => fetch(input),
  ) {}

  /** Absolute-or-relative URL of a kb file. */
  url(rel: string): string {
    return this.base + rel;
  }

  private load<T>(rel: string, kind: 'json' | 'text'): Promise<T | null> {
    const url = this.url(rel);
    const key = `${kind}:${url}`;
    let p = this.cache.get(key) as Promise<T | null> | undefined;
    if (!p) {
      p = (async () => {
        const res = await this.fetchFn(url);
        if (res.status === 404) return null;
        if (!res.ok) throw new HttpError(url, res.status);
        return (kind === 'json' ? await res.json() : await res.text()) as T;
      })();
      p.catch(() => this.cache.delete(key));
      this.cache.set(key, p);
    }
    return p;
  }

  json<T>(rel: string): Promise<T | null> {
    return this.load<T>(rel, 'json');
  }

  text(rel: string): Promise<string | null> {
    return this.load<string>(rel, 'text');
  }

  catalog(): Promise<Catalog | null> {
    return this.json<Catalog>('catalog.json');
  }

  /** Data access scoped to one study. */
  study(name: string): StudyData {
    return new StudyData(this, encodeURIComponent(name) + '/');
  }
}

export class StudyData {
  constructor(
    private readonly kb: KbClient,
    private readonly prefix: string,
  ) {}

  private snap(sha: string, rel: string): string {
    return `${this.prefix}snapshots/${encodeURIComponent(sha)}/${rel}`;
  }

  private diff(a: string, b: string, rel: string): string {
    return `${this.prefix}diffs/${encodeURIComponent(a)}..${encodeURIComponent(b)}/${rel}`;
  }

  study(): Promise<Study | null> {
    return this.kb.json<Study>(this.prefix + 'study.json');
  }

  /** Content of a blob (blobs/<h[:2]>/<hash>.txt). */
  blob(hash: string): Promise<string | null> {
    return this.kb.text(`${this.prefix}blobs/${hash.slice(0, 2)}/${hash}.txt`);
  }

  tree(sha: string): Promise<Tree | null> {
    return this.kb.json<Tree>(this.snap(sha, 'tree.json'));
  }

  symbols(sha: string): Promise<Symbols | null> {
    return this.kb.json<Symbols>(this.snap(sha, 'symbols.json'));
  }

  explain(sha: string, path: string): Promise<Explain | null> {
    return this.kb.json<Explain>(this.snap(sha, `explain/${encodePath(path)}.json`));
  }

  /** Directory summary; "" is the repo root (dirs/_root.json). */
  dir(sha: string, path: string): Promise<DirSummary | null> {
    const rel = path === '' ? '_root' : encodePath(path);
    return this.kb.json<DirSummary>(this.snap(sha, `dirs/${rel}.json`));
  }

  overview(sha: string): Promise<string | null> {
    return this.kb.text(this.snap(sha, 'overview.md'));
  }

  links(sha: string): Promise<Links | null> {
    return this.kb.json<Links>(this.snap(sha, 'links.json'));
  }

  /** Tours of a snapshot, derived from links.json doc keys "tours/<id>.json" (sorted by id). */
  async tours(sha: string): Promise<TourListEntry[]> {
    const links = await this.links(sha);
    if (!links) return [];
    const ids = Object.keys(links.docs)
      .map((k) => TOUR_KEY.exec(k)?.[1])
      .filter((id): id is string => id !== undefined);
    return [...new Set(ids)].sort().map((id) => ({ id }));
  }

  tour(sha: string, id: string): Promise<Tour | null> {
    return this.kb.json<Tour>(this.snap(sha, `tours/${encodeURIComponent(id)}.json`));
  }

  /**
   * Archify diagrams of a snapshot, derived from links.json markers of kind
   * "archify" (unique names, sorted). A name is broken when no marker resolves
   * it (no diagrams/<name>.html). Mermaid diagrams are inline and not listed.
   */
  async diagrams(sha: string): Promise<DiagramEntry[]> {
    const links = await this.links(sha);
    if (!links) return [];
    const broken = new Map<string, boolean>();
    for (const markers of Object.values(links.docs)) {
      for (const m of markers) {
        if (m.kind !== 'archify') continue;
        const name = ARCHIFY_RAW.exec(m.raw)?.[1];
        if (name) broken.set(name, (broken.get(name) ?? true) && !(m.status === 'exact' && isDiagramName(name)));
      }
    }
    return [...broken.keys()].sort().map((name) => ({ name, broken: broken.get(name)! }));
  }

  /** Relative URL of an archify diagram page (for an iframe); null for an unsafe name. */
  diagramUrl(sha: string, name: string): string | null {
    if (!isDiagramName(name)) return null;
    return this.kb.url(this.snap(sha, `diagrams/${encodeURIComponent(name)}.html`));
  }

  graph(sha: string): Promise<Graph | null> {
    return this.kb.json<Graph>(this.snap(sha, 'graph/graph.json'));
  }

  issues(sha: string): Promise<Issues | null> {
    return this.kb.json<Issues>(this.snap(sha, 'issues.json'));
  }

  changes(a: string, b: string): Promise<Changes | null> {
    return this.kb.json<Changes>(this.diff(a, b, 'changes.json'));
  }

  /** Global explanation of a diff (explain.md). */
  diffExplain(a: string, b: string): Promise<string | null> {
    return this.kb.text(this.diff(a, b, 'explain.md'));
  }

  diffFileExplain(a: string, b: string, path: string): Promise<DiffFileExplain | null> {
    return this.kb.json<DiffFileExplain>(this.diff(a, b, `explain/${encodePath(path)}.json`));
  }
}
