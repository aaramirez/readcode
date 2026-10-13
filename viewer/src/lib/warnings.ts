// issues.json → warnings per file / directory.
//
// An issue's `file` is the snapshot-relative doc it concerns ("explain/<path>.json",
// "dirs/<path>.json", "tours/<id>.json", "overview.md"…) or a repo path.

import type { Issue } from './types';

export interface IssueIndex {
  files: Map<string, Issue[]>;
  /** Directory path ("" = root) → issues of its summary. */
  dirs: Map<string, Issue[]>;
  /** Issues not tied to a file or directory of the tree. */
  other: Issue[];
}

const EXPLAIN = /^explain\/(.+)\.json$/;
const DIRS = /^dirs\/(.+)\.json$/;

function push(map: Map<string, Issue[]>, key: string, issue: Issue) {
  const list = map.get(key);
  if (list) list.push(issue);
  else map.set(key, [issue]);
}

export function issuesByPath(issues: Issue[], paths: Set<string>): IssueIndex {
  const out: IssueIndex = { files: new Map(), dirs: new Map(), other: [] };
  for (const issue of issues) {
    const f = issue.file;
    const ex = f ? EXPLAIN.exec(f) : null;
    const dir = f ? DIRS.exec(f) : null;
    if (ex) push(out.files, ex[1], issue);
    else if (dir) push(out.dirs, dir[1] === '_root' ? '' : dir[1], issue);
    else if (f && paths.has(f)) push(out.files, f, issue);
    else out.other.push(issue);
  }
  return out;
}

/** Warning count per tree row path (files and directories; the root row is not marked). */
export function warningCounts(index: IssueIndex): Map<string, number> {
  const out = new Map<string, number>();
  for (const [p, list] of index.files) out.set(p, list.length);
  for (const [p, list] of index.dirs) if (p !== '') out.set(p, (out.get(p) ?? 0) + list.length);
  return out;
}
