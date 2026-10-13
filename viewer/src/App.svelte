<script lang="ts">
  import { onMount } from 'svelte';
  import CodeView from './components/CodeView.svelte';
  import ExplainPanel from './components/ExplainPanel.svelte';
  import FileTree from './components/FileTree.svelte';
  import OverviewView from './components/OverviewView.svelte';
  import Splitter from './components/Splitter.svelte';
  import StudyList from './components/StudyList.svelte';
  import TopBar from './components/TopBar.svelte';
  import { KbClient } from './lib/data';
  import { loadPref, savePref, type Theme } from './lib/prefs';
  import {
    latestSnapshot,
    navigate,
    parse,
    resolveSha,
    routeSha,
    routeStudy,
    type LineRange,
    type Route,
  } from './lib/router';
  import type { Catalog, Study, Tree } from './lib/types';

  const kb = new KbClient('kb/');

  // ---- routing
  let route = $state<Route>(parse(location.hash));
  onMount(() => {
    const onHash = () => (route = parse(location.hash));
    window.addEventListener('hashchange', onHash);
    return () => window.removeEventListener('hashchange', onHash);
  });

  // ---- catalog / study / snapshot
  let catalog = $state<Catalog | null>(null);
  let catalogError = $state<string | null>(null);
  kb.catalog().then(
    (c) => (catalog = c),
    (e: Error) => (catalogError = e.message),
  );

  const studyName = $derived(routeStudy(route));
  const data = $derived(studyName ? kb.study(studyName) : null);

  type Loaded<T> = { key: string; value: T | null; error: string | null } | null;
  let studyRes = $state<Loaded<Study>>(null);
  $effect(() => {
    const name = studyName;
    const d = data;
    if (!name || !d) return;
    if (studyRes?.key === name) return;
    d.study().then(
      (s) => {
        if (studyName === name) studyRes = { key: name, value: s, error: null };
      },
      (e: Error) => {
        if (studyName === name) studyRes = { key: name, value: null, error: e.message };
      },
    );
  });
  const study = $derived(studyRes && studyRes.key === studyName ? studyRes.value : null);
  const studyLoading = $derived(!!studyName && studyRes?.key !== studyName);

  const sha = $derived.by(() => {
    if (!study) return null;
    const prefix = routeSha(route);
    return prefix ? resolveSha(study, prefix) : (latestSnapshot(study)?.sha ?? null);
  });

  let treeRes = $state<Loaded<Tree>>(null);
  $effect(() => {
    const d = data;
    const s = sha;
    if (!d || !s) return;
    const key = `${studyName}@${s}`;
    if (treeRes?.key === key) return;
    d.tree(s).then(
      (t) => (treeRes = { key, value: t, error: null }),
      (e: Error) => (treeRes = { key, value: null, error: e.message }),
    );
  });
  const treeKey = $derived(`${studyName}@${sha}`);
  const tree = $derived(treeRes && treeRes.key === treeKey ? treeRes.value : null);

  // ---- center tabs
  type Tab = 'code' | 'graph' | 'diagrams' | 'overview' | 'tours';
  const TABS: { id: Tab; label: string }[] = [
    { id: 'code', label: 'Código' },
    { id: 'graph', label: 'Grafo' },
    { id: 'diagrams', label: 'Diagramas' },
    { id: 'overview', label: 'Overview' },
    { id: 'tours', label: 'Tours' },
  ];
  let tab = $state<Tab>('overview');
  let lastFile = $state<{ study: string; path: string; range?: LineRange } | null>(null);

  $effect(() => {
    const r = route;
    switch (r.kind) {
      case 'study':
      case 'overview':
        tab = 'overview';
        break;
      case 'file':
        tab = 'code';
        lastFile = { study: r.study, path: r.path, range: r.range };
        break;
      case 'graph':
        tab = 'graph';
        break;
      case 'diagrams':
        tab = 'diagrams';
        break;
      case 'tour':
        tab = 'tours';
        break;
    }
  });

  const currentFile = $derived(lastFile && lastFile.study === studyName ? lastFile : null);

  function selectTab(t: Tab) {
    if (!studyName || !sha) return;
    if (t === 'overview') navigate({ kind: 'overview', study: studyName, sha });
    else if (t === 'graph') navigate({ kind: 'graph', study: studyName, sha });
    else if (t === 'diagrams') navigate({ kind: 'diagrams', study: studyName, sha });
    else if (t === 'code' && currentFile) {
      navigate({ kind: 'file', study: studyName, sha, path: currentFile.path, range: currentFile.range });
    } else tab = t;
  }

  const treeSelected = $derived(
    route.kind === 'file' ? { kind: 'file' as const, path: route.path } : route.kind === 'dir' ? { kind: 'dir' as const, path: route.path } : null,
  );
  const panelTarget = $derived(treeSelected ?? { kind: 'dir' as const, path: '' });

  // ---- top bar actions
  function onStudy(name: string) {
    navigate({ kind: 'study', study: name });
  }

  async function onSha(newSha: string) {
    if (!studyName || !data) return;
    const r = route;
    if (r.kind === 'file' || r.kind === 'dir') {
      const t = await data.tree(newSha).catch(() => null);
      const keep =
        r.kind === 'file'
          ? !!t?.files.some((f) => f.path === r.path)
          : r.path === '' || !!t?.files.some((f) => f.path.startsWith(r.path + '/'));
      if (keep) return navigate({ ...r, sha: newSha });
      return navigate({ kind: 'overview', study: studyName, sha: newSha });
    }
    if (r.kind === 'graph' || r.kind === 'diagrams' || r.kind === 'tour') return navigate({ ...r, sha: newSha });
    navigate({ kind: 'overview', study: studyName, sha: newSha });
  }

  // ---- theme
  let theme = $state<Theme>(loadPref<Theme>('theme', 'auto'));
  $effect(() => {
    if (theme === 'auto') delete document.documentElement.dataset.theme;
    else document.documentElement.dataset.theme = theme;
  });
  function cycleTheme() {
    theme = theme === 'auto' ? 'light' : theme === 'light' ? 'dark' : 'auto';
    savePref('theme', theme);
  }

  // ---- resizable panes
  const panes = loadPref<{ left: number; right: number }>('panes', { left: 260, right: 380 });
  let leftW = $state(Number(panes.left) || 260);
  let rightW = $state(Number(panes.right) || 380);
  const clamp = (w: number) => Math.max(150, Math.min(w, window.innerWidth * 0.6));
  const savePanes = () => savePref('panes', { left: leftW, right: rightW });
</script>

<div class="app">
  <TopBar {catalog} {studyName} {study} {sha} {theme} {onStudy} {onSha} onTheme={cycleTheme} />

  {#if route.kind === 'notfound'}
    <div class="empty">Ruta no válida: <code>{route.hash}</code>. <a href="#/">Volver a la lista de estudios</a>.</div>
  {:else if route.kind === 'catalog'}
    {#if catalogError}
      <div class="empty">Error al cargar el catálogo: {catalogError}</div>
    {:else}
      <StudyList {catalog} />
    {/if}
  {:else if studyLoading}
    <div class="empty">Cargando estudio…</div>
  {:else if studyRes?.error}
    <div class="empty">Error al cargar el estudio: {studyRes.error}</div>
  {:else if !study}
    <div class="empty">El estudio <code>{studyName}</code> no existe. <a href="#/">Ver estudios</a>.</div>
  {:else if study.schemaVersion !== 1}
    <div class="empty">Estudio incompatible: schemaVersion {study.schemaVersion} (este visor admite 1).</div>
  {:else if !sha}
    <div class="empty">
      {study.snapshots.length === 0 ? 'El estudio no tiene commits.' : `Commit no encontrado en el estudio: ${routeSha(route)}.`}
    </div>
  {:else if data}
    <div class="panes">
      <aside class="pane" style="width: {leftW}px">
        {#if tree}
          <FileTree
            {tree}
            selected={treeSelected}
            onFile={(path) => navigate({ kind: 'file', study: study.name, sha, path })}
            onDir={(path) => navigate({ kind: 'dir', study: study.name, sha, path })}
          />
        {:else if treeRes?.key === treeKey && treeRes.error}
          <div class="empty">Error al cargar tree.json: {treeRes.error}</div>
        {:else if treeRes?.key === treeKey}
          <div class="empty">Este commit no tiene tree.json.</div>
        {:else}
          <div class="empty">Cargando…</div>
        {/if}
      </aside>
      <Splitter onDrag={(dx) => (leftW = clamp(leftW + dx))} onEnd={savePanes} />
      <main class="pane center">
        <div class="tabs" role="tablist">
          {#each TABS as t (t.id)}
            <button role="tab" class:active={tab === t.id} aria-selected={tab === t.id} onclick={() => selectTab(t.id)}>
              {t.label}
            </button>
          {/each}
        </div>
        <div class="tab-body">
          {#if route.kind === 'diff'}
            <div class="empty">La vista de comparación estará disponible próximamente.</div>
          {:else if tab === 'overview'}
            <OverviewView {data} {sha} />
          {:else if tab === 'code'}
            {#if currentFile && tree}
              <CodeView {data} {tree} path={currentFile.path} range={currentFile.range} />
            {:else}
              <div class="empty">Selecciona un archivo en el árbol.</div>
            {/if}
          {:else}
            <div class="empty">Próximamente.</div>
          {/if}
        </div>
      </main>
      <Splitter onDrag={(dx) => (rightW = clamp(rightW - dx))} onEnd={savePanes} />
      <aside class="pane" style="width: {rightW}px">
        <ExplainPanel {data} study={study.name} {sha} target={panelTarget} />
      </aside>
    </div>
  {/if}
</div>

<style>
  .app {
    display: flex;
    flex-direction: column;
    height: 100%;
  }
  .panes {
    display: flex;
    flex: 1;
    min-height: 0;
  }
  .pane {
    flex: none;
    min-width: 0;
    overflow: hidden;
    display: flex;
    flex-direction: column;
  }
  .center {
    flex: 1;
  }
  .tabs {
    display: flex;
    gap: 2px;
    padding: 4px 6px 0;
    border-bottom: 1px solid var(--border);
    flex: none;
  }
  .tabs button {
    border: 1px solid transparent;
    border-bottom: none;
    border-radius: 4px 4px 0 0;
    background: transparent;
    padding: 4px 12px;
  }
  .tabs button.active {
    background: var(--bg);
    border-color: var(--border);
    margin-bottom: -1px;
    font-weight: 600;
  }
  .tab-body {
    flex: 1;
    min-height: 0;
    overflow: hidden;
  }
</style>
