<script lang="ts">
  // Application shell: top bar, snapshot-switch notice, theme, the Compare and
  // search dialogs, and the global keyboard shortcuts. The page body (study list,
  // status messages or the workspace) is the `children` snippet.
  import { onMount, type Snippet } from 'svelte';
  import CompareDialog from './CompareDialog.svelte';
  import SearchPalette from './SearchPalette.svelte';
  import TopBar from './TopBar.svelte';
  import type { StudyData } from '../lib/data';
  import type { Nav } from '../lib/nav';
  import { loadPref, savePref, type Theme } from '../lib/prefs';
  import { resolveSha, type Route } from '../lib/router';
  import { routeOnSnapshotSwitch } from '../lib/snapshots';
  import { themeState } from '../lib/theme.svelte';
  import type { Catalog, Study, Tree } from '../lib/types';

  interface Props {
    nav: Nav;
    route: Route;
    catalog: Catalog | null;
    studyName: string | null;
    study: Study | null;
    sha: string | null;
    tree: Tree | null;
    data: StudyData | null;
    /** The workspace is shown (a readable study at a known snapshot). */
    ready: boolean;
    /** Step the playing tour with [ and ] (null: no tour playing). */
    stepTour: ((delta: -1 | 1) => void) | null;
    children: Snippet;
  }

  let { nav, route, catalog, studyName, study, sha, tree, data, ready, stepTour, children }: Props = $props();

  // ---- top bar actions
  let notice = $state<string | null>(null);
  let compareOpen = $state(false);
  let searchOpen = $state(false);
  $effect(() => {
    void studyName;
    notice = null;
  });

  function onStudy(name: string) {
    nav.go({ kind: 'study', study: name });
  }

  async function onSha(newSha: string) {
    if (!studyName || !data) return;
    const r = route;
    const t = await data.tree(newSha).catch(() => null);
    const res = routeOnSnapshotSwitch(r, newSha, t);
    notice = res.notice;
    nav.go(res.route);
  }

  function onCompare(a: string, b: string) {
    compareOpen = false;
    if (studyName) nav.go({ kind: 'diff', study: studyName, a, b });
  }

  const diffLabel = $derived.by(() => {
    if (route.kind !== 'diff' || !study) return null;
    const a = resolveSha(study, route.a);
    const b = resolveSha(study, route.b);
    return a && b ? `${a.slice(0, 7)} → ${b.slice(0, 7)}` : null;
  });

  // ---- keyboard: Ctrl/Cmd+K search, [ ] tour steps
  function typing(e: KeyboardEvent): boolean {
    const t = e.target as HTMLElement | null;
    return !!t && (t.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName));
  }
  onMount(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && !e.altKey && e.key.toLowerCase() === 'k') {
        // the compare dialog is modal (top layer): the palette would open underneath it
        if (!data || !sha || !tree || compareOpen) return;
        e.preventDefault();
        searchOpen = true;
        return;
      }
      if (searchOpen || compareOpen || typing(e) || e.ctrlKey || e.metaKey || e.altKey) return;
      if (stepTour && (e.key === '[' || e.key === ']')) {
        e.preventDefault();
        stepTour(e.key === '[' ? -1 : 1);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  });

  // ---- theme
  let theme = $state<Theme>(loadPref<Theme>('theme', 'auto'));
  const darkQuery = window.matchMedia('(prefers-color-scheme: dark)');
  let osDark = $state(darkQuery.matches);
  onMount(() => {
    const onChange = () => (osDark = darkQuery.matches);
    darkQuery.addEventListener('change', onChange);
    return () => darkQuery.removeEventListener('change', onChange);
  });
  $effect(() => {
    if (theme === 'auto') delete document.documentElement.dataset.theme;
    else document.documentElement.dataset.theme = theme;
    themeState.dark = theme === 'dark' || (theme === 'auto' && osDark);
  });
  function cycleTheme() {
    theme = theme === 'auto' ? 'light' : theme === 'light' ? 'dark' : 'auto';
    savePref('theme', theme);
  }
</script>

<div class="app">
  <TopBar
    {catalog}
    {studyName}
    {study}
    {sha}
    {theme}
    {onStudy}
    {onSha}
    onTheme={cycleTheme}
    onBack={nav.back}
    onForward={nav.forward}
    onCompare={ready ? () => (compareOpen = true) : null}
    onSearch={ready && tree ? () => (searchOpen = true) : null}
    {diffLabel}
  />
  {#if notice}
    <div class="notice" role="status">
      <span>{notice}</span>
      <button aria-label="Cerrar aviso" onclick={() => (notice = null)}>✕</button>
    </div>
  {/if}

  {@render children()}

  {#if ready && data && study && sha}
    {#if compareOpen}
      <CompareDialog {data} {study} {sha} {onCompare} onClose={() => (compareOpen = false)} />
    {/if}
    {#if searchOpen && tree}
      <SearchPalette {data} study={study.name} {sha} {tree} onClose={() => (searchOpen = false)} />
    {/if}
  {/if}
</div>

<style>
  .app {
    display: flex;
    flex-direction: column;
    height: 100%;
  }
  .notice {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 4px 12px;
    background: var(--bg-highlight);
    border-bottom: 1px solid var(--border);
    font-size: 13px;
  }
  .notice span {
    flex: 1;
  }
  .notice button {
    border: none;
    background: transparent;
  }
</style>
