// Hand-written TypeScript mirror of schemas/*.schema.json (the study format contract).

/** [startLine, endLine], 1-based inclusive. */
export type Range = [number, number];

export interface Repo {
  url: string;
  localPath?: string;
}

// catalog.schema.json
export interface CatalogEntry {
  name: string;
  title: string;
  repo: Repo;
  snapshots: number;
  updated: string;
}

export interface Catalog {
  schemaVersion: 1;
  studies: CatalogEntry[];
}

// study.schema.json
export type SnapshotStatus = 'indexed' | 'explained' | 'partial';

export interface Snapshot {
  sha: string;
  date: string;
  message: string;
  status: SnapshotStatus;
}

export interface Study {
  schemaVersion: number;
  name: string;
  title: string;
  repo: Repo;
  language: string;
  exclude: string[];
  tools: { graphify: boolean; archify: boolean };
  snapshots: Snapshot[];
}

// tree.schema.json
export interface TreeFile {
  path: string;
  blob: string;
  language: string | null;
  lines: number;
  bytes: number;
  indexed: boolean;
  excluded?: false;
}

export type ExcludeReason = 'gitignore' | 'default' | 'study' | 'binary' | 'size';

export interface ExcludedPath {
  path: string;
  reason: ExcludeReason;
}

export interface Tree {
  schemaVersion: 1;
  sha: string;
  files: TreeFile[];
  excluded: ExcludedPath[];
}

// symbols.schema.json
export type SymbolKind =
  | 'function'
  | 'method'
  | 'class'
  | 'interface'
  | 'type'
  | 'struct'
  | 'variable'
  | 'constant'
  | 'module'
  | 'table'
  | 'other';

export interface SymbolDef {
  name: string;
  kind: SymbolKind;
  range: Range;
  parent?: string;
}

export interface SymbolRef {
  name: string;
  /** 1-based line. */
  line: number;
  /** 0-based column. */
  col: number;
}

export interface SymbolImport {
  module: string;
  line: number;
  resolved?: string | null;
}

export interface FileSymbols {
  defs: SymbolDef[];
  refs: SymbolRef[];
  imports: SymbolImport[];
}

export interface Symbols {
  schemaVersion: 1;
  sha: string;
  files: Record<string, FileSymbols>;
}

// explain.schema.json
export interface Block {
  id: string;
  range: Range;
  title: string;
  body: string;
}

export interface Explain {
  schemaVersion: 1;
  path: string;
  blobHash: string;
  summary: string;
  blocks: Block[];
}

// dir.schema.json
export interface DirChild {
  path: string;
  kind: 'file' | 'dir';
  oneLine: string;
}

export interface DirSummary {
  schemaVersion: 1;
  /** "" for the repo root. */
  path: string;
  summary: string;
  children: DirChild[];
}

// tour.schema.json
export interface TourStep {
  path: string;
  range: Range;
  title: string;
  body: string;
}

export interface Tour {
  schemaVersion: 1;
  id: string;
  title: string;
  description: string;
  steps: TourStep[];
}

// search.schema.json (snapshots/<sha>/search.json, written by `readcode validate`)
export interface SearchEntry {
  path: string;
  blockId: string;
  title: string;
  range: Range;
}

// links.schema.json
export type MarkerKind = 'symbol' | 'lines' | 'archify' | 'invalid';
export type MarkerStatus = 'exact' | 'ambiguous' | 'broken';

export interface LinkCandidate {
  target: string;
  range: Range;
}

export interface LinkMarker {
  raw: string;
  kind: MarkerKind;
  status: MarkerStatus;
  target?: string;
  range?: Range;
  /** Diff links only: "A" when the marker only resolves in snapshot A; omitted = B. */
  snapshot?: 'A' | 'B';
  candidates?: LinkCandidate[];
}

export interface Links {
  schemaVersion: 1;
  sha: string;
  /** Explicit list of diagrams/ files (absent in v1 kbs: the viewer derives the archify list). */
  diagrams?: { name: string; kind: DiagramKind }[];
  /** Doc key (e.g. "overview.md", "tours/login.json") → markers in that doc. */
  docs: Record<string, LinkMarker[]>;
}

// changes.schema.json
export type ChangeStatus = 'added' | 'modified' | 'deleted' | 'renamed';

export interface Hunk {
  fromRange: Range | null;
  toRange: Range | null;
  header?: string;
}

export interface ChangedFile {
  path: string;
  status: ChangeStatus;
  oldPath?: string;
  fromBlob?: string;
  toBlob?: string;
  /** Modified, but only line endings differ (hunks is empty). Absent in v1 kbs. */
  eolOnly?: boolean;
  hunks: Hunk[];
}

export interface Changes {
  schemaVersion: 1;
  from: string;
  to: string;
  files: ChangedFile[];
}

// diff-explain.schema.json
export interface DiffFileExplain {
  schemaVersion: 1;
  path: string;
  summary: string;
  hunks: { index: number; body: string }[];
}

// issues.schema.json
export interface Issue {
  file?: string;
  problem: string;
  hint?: string;
  /** Machine-readable code of a warning (e.g. 'legacy-root'). */
  code?: string;
  source: 'validate' | 'generator' | 'tool';
}

export interface Issues {
  schemaVersion: 1;
  issues: Issue[];
}

/** graph/graph.json is Graphify output; its shape is owned by Graphify. */
export type Graph = Record<string, unknown>;

/** Entry of the derived tours list (from links.json doc keys). */
export interface TourListEntry {
  id: string;
}

export type DiagramKind = 'archify' | 'mermaid';

/** A diagram of a snapshot (archify broken: referenced but no diagrams/<name>.html). */
export interface DiagramEntry {
  name: string;
  kind: DiagramKind;
  broken: boolean;
}
