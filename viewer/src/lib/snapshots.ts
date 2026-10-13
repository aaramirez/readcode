// Commit selector: where to go when switching to another snapshot.

import type { Route } from './router';
import type { Tree } from './types';

export interface SwitchResult {
  route: Route;
  /** Shown to the user when the current file/dir could not be kept. */
  notice: string | null;
}

function hasFile(tree: Tree | null, path: string): boolean {
  return !!tree?.files.some((f) => f.path === path);
}

function hasDir(tree: Tree | null, path: string): boolean {
  return path === '' || !!tree?.files.some((f) => f.path.startsWith(path + '/'));
}

/**
 * Route for `route` in snapshot `sha` (whose tree.json is `tree`): the same
 * file/dir when it exists there, else the overview with a notice.
 */
export function routeOnSnapshotSwitch(route: Route, sha: string, tree: Tree | null): SwitchResult {
  const short = sha.slice(0, 7);
  switch (route.kind) {
    case 'file':
      return hasFile(tree, route.path)
        ? { route: { ...route, sha }, notice: null }
        : { route: { kind: 'overview', study: route.study, sha }, notice: `«${route.path}» no existe en el commit ${short}; se muestra el overview.` };
    case 'dir':
      return hasDir(tree, route.path)
        ? { route: { ...route, sha }, notice: null }
        : { route: { kind: 'overview', study: route.study, sha }, notice: `«${route.path}/» no existe en el commit ${short}; se muestra el overview.` };
    case 'diff':
      if (route.path) return routeOnSnapshotSwitch({ kind: 'file', study: route.study, sha, path: route.path }, sha, tree);
      return { route: { kind: 'overview', study: route.study, sha }, notice: null };
    case 'graph':
      return {
        route: route.path && hasFile(tree, route.path) ? { ...route, sha } : { kind: 'graph', study: route.study, sha },
        notice: null,
      };
    case 'tour':
    case 'diagrams':
      return { route: { ...route, sha }, notice: null };
    case 'catalog':
    case 'notfound':
      return { route, notice: null };
    default:
      return { route: { kind: 'overview', study: route.study, sha }, notice: null };
  }
}
