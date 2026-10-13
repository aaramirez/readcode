import { get } from 'svelte/store';
import { describe, expect, it } from 'vitest';
import { createNav, nextState, type NavHost } from './nav';

const SHA = 'b42f63fb2414b4d4d830af722a64255504a80ee8';

/** In-memory stand-in for window: a hash history with back/forward. */
class FakeHost implements NavHost {
  entries: string[];
  index = 0;
  private listeners = new Set<() => void>();
  readonly history = {
    back: () => this.move(-1),
    forward: () => this.move(1),
  };
  readonly location: { hash: string };

  constructor(hash = '') {
    this.entries = [hash];
    const host = this;
    this.location = {
      get hash() {
        return host.entries[host.index];
      },
      set hash(h: string) {
        const next = h.startsWith('#') ? h : '#' + h;
        if (next === host.entries[host.index]) return;
        host.entries = [...host.entries.slice(0, host.index + 1), next];
        host.index++;
        host.fire();
      },
    };
  }
  addEventListener(_type: 'hashchange', fn: () => void) {
    this.listeners.add(fn);
  }
  removeEventListener(_type: 'hashchange', fn: () => void) {
    this.listeners.delete(fn);
  }
  get listenerCount() {
    return this.listeners.size;
  }
  private move(delta: number) {
    const i = this.index + delta;
    if (i < 0 || i >= this.entries.length) return;
    this.index = i;
    this.fire();
  }
  private fire() {
    for (const fn of this.listeners) fn();
  }
}

describe('createNav', () => {
  it('starts from the current hash', () => {
    const host = new FakeHost(`#/fixture/${SHA}/f/app/main.py`);
    const nav = createNav(host);
    expect(get(nav).route).toEqual({ kind: 'file', study: 'fixture', sha: SHA, path: 'app/main.py' });
  });

  it('go() writes the hash and reports whether it changed', () => {
    const host = new FakeHost('#/');
    const nav = createNav(host);
    const stop = nav.subscribe(() => {});
    expect(nav.go({ kind: 'study', study: 'fixture' })).toBe(true);
    expect(host.location.hash).toBe('#/fixture');
    expect(get(nav).route).toEqual({ kind: 'study', study: 'fixture' });
    expect(nav.go({ kind: 'study', study: 'fixture' })).toBe(false);
    expect(host.entries).toEqual(['#/', '#/fixture']);
    stop();
  });

  it('back() and forward() walk the browser history', () => {
    const host = new FakeHost('#/');
    const nav = createNav(host);
    const seen: string[] = [];
    const stop = nav.subscribe((s) => seen.push(s.route.kind));
    nav.go({ kind: 'study', study: 'fixture' });
    nav.go({ kind: 'overview', study: 'fixture', sha: SHA });
    nav.back();
    expect(get(nav).route).toEqual({ kind: 'study', study: 'fixture' });
    nav.back();
    expect(get(nav).route).toEqual({ kind: 'catalog' });
    nav.forward();
    nav.forward();
    expect(get(nav).route).toEqual({ kind: 'overview', study: 'fixture', sha: SHA });
    expect(seen).toEqual(['catalog', 'study', 'overview', 'study', 'catalog', 'study', 'overview']);
    stop();
  });

  it('follows hash changes made outside the store (links, address bar)', () => {
    const host = new FakeHost('#/');
    const nav = createNav(host);
    const stop = nav.subscribe(() => {});
    host.location.hash = `#/fixture/${SHA}/graph`;
    expect(get(nav).route).toEqual({ kind: 'graph', study: 'fixture', sha: SHA });
    stop();
  });

  it('listens only while subscribed and catches up on resubscribe', () => {
    const host = new FakeHost('#/');
    const nav = createNav(host);
    expect(host.listenerCount).toBe(0);
    const stop = nav.subscribe(() => {});
    expect(host.listenerCount).toBe(1);
    stop();
    expect(host.listenerCount).toBe(0);
    host.location.hash = '#/fixture';
    expect(get(nav).route).toEqual({ kind: 'study', study: 'fixture' });
  });
});

describe('nextState: last code location', () => {
  it('remembers the last file or directory across other routes', () => {
    let s = nextState(null, { kind: 'file', study: 'fixture', sha: SHA, path: 'a.py', range: { start: 3, end: 5 } });
    expect(s.lastCode).toEqual({ study: 'fixture', kind: 'file', path: 'a.py', range: { start: 3, end: 5 } });
    s = nextState(s, { kind: 'graph', study: 'fixture', sha: SHA });
    s = nextState(s, { kind: 'catalog' });
    expect(s.lastCode).toEqual({ study: 'fixture', kind: 'file', path: 'a.py', range: { start: 3, end: 5 } });
    s = nextState(s, { kind: 'dir', study: 'fixture', sha: SHA, path: 'app' });
    expect(s.lastCode).toEqual({ study: 'fixture', kind: 'dir', path: 'app' });
  });

  it('starts empty when the first route is not a file or directory', () => {
    expect(nextState(null, { kind: 'catalog' })).toEqual({ route: { kind: 'catalog' }, lastCode: null });
  });
});
