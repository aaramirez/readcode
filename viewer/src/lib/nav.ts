// Navigation store of the viewer: the current route (parsed from location.hash)
// plus the route-derived state that outlives a single route.
//
// The browser history is the navigation history (see router.ts): go() writes
// the hash, back()/forward() delegate to history, and every hashchange
// (links, address bar, ← →) is parsed into a new state. The host is injectable
// so the store can be tested without a browser.

import { writable, type Readable } from 'svelte/store';
import { format, parse, type LineRange, type Route } from './router';

/** Last file or directory shown in the Código tab (a d/ route shows the dir there). */
export interface CodeLocation {
  study: string;
  kind: 'file' | 'dir';
  path: string;
  range?: LineRange;
}

export interface NavState {
  route: Route;
  lastCode: CodeLocation | null;
}

/** The part of `window` the store uses. */
export interface NavHost {
  location: { hash: string };
  history: { back(): void; forward(): void };
  addEventListener(type: 'hashchange', listener: () => void): void;
  removeEventListener(type: 'hashchange', listener: () => void): void;
}

export interface Nav extends Readable<NavState> {
  /** Navigate to a route; false when the hash is already that route's (no history entry). */
  go(route: Route): boolean;
  back(): void;
  forward(): void;
}

/** State after entering `route`. */
export function nextState(prev: NavState | null, route: Route): NavState {
  let lastCode = prev?.lastCode ?? null;
  if (route.kind === 'file') lastCode = { study: route.study, kind: 'file', path: route.path, range: route.range };
  else if (route.kind === 'dir') lastCode = { study: route.study, kind: 'dir', path: route.path };
  return { route, lastCode };
}

export function createNav(host: NavHost = window): Nav {
  let hash = host.location.hash;
  const store = writable<NavState>(nextState(null, parse(hash)), (_set, update) => {
    const sync = () => {
      hash = host.location.hash;
      update((s) => nextState(s, parse(hash)));
    };
    // the hash may have moved while nobody was listening
    if (host.location.hash !== hash) sync();
    host.addEventListener('hashchange', sync);
    return () => host.removeEventListener('hashchange', sync);
  });
  return {
    subscribe: store.subscribe,
    go(route) {
      const target = format(route);
      if (host.location.hash === target) return false;
      host.location.hash = target;
      return true;
    },
    back: () => host.history.back(),
    forward: () => host.history.forward(),
  };
}
