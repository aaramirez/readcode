<script lang="ts">
  import { onMount } from 'svelte';
  import CodeView from './components/CodeView.svelte';
  import CompareDialog from './components/CompareDialog.svelte';
  import DiagramsView from './components/DiagramsView.svelte';
  import DiffPanel from './components/DiffPanel.svelte';
  import DiffView from './components/DiffView.svelte';
  import DirView from './components/DirView.svelte';
  import ExplainPanel from './components/ExplainPanel.svelte';
  import FileTree from './components/FileTree.svelte';
  import GraphView from './components/GraphView.svelte';
  import OverviewView from './components/OverviewView.svelte';
  import SearchPalette from './components/SearchPalette.svelte';
  import Splitter from './components/Splitter.svelte';
  import StudyList from './components/StudyList.svelte';
  import TopBar from './components/TopBar.svelte';
  import TourPanel from './components/TourPanel.svelte';
  import ToursView from './components/ToursView.svelte';
  import { KbClient } from './lib/data';
  import { diffBadges, diffLinkSha, diffTree } from './lib/diff';
  import { loadPref, savePref, type Theme } from './lib/prefs';
  import {
    format,
    latestSnapshot,
    navigate,
    parse,
    resolveSha,
    routeSha,
    routeStudy,
    type LineRange,
    type Route,
  } from './lib/router';
  import { routeOnSnapshotSwitch } from './lib/snapshots';
  import { themeState } from './lib/theme.svelte';
  import { clampStep, stepNav } from './lib/tours';
  import type { Block, Catalog, Changes, Issue, Study, Tour, Tree } from './lib/types';
  import { issuesByPath, warningCounts } from './lib/warnings';

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

  // In the diff view the "current" snapshot is B.
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

  // ---- data-dependent tabs (hidden when their data is missing)
  let avail = $state<{ key: string; graph: boolean; tours: boolean; diagrams: boolean } | null>(null);
  $effect(() => {
    const d = data;
    const s = sha;
    const st = study;
    if (!d || !s || !st) return;
    const key = treeKey;
    if (avail?.key === key) return;
    const no = () => false;
    Promise.all([
      // graphify off → no graph.json to look for
      st.tools?.graphify === false ? false : d.graph(s).then((g) => !!g, no),
      d.tours(s).then((l) => l.length > 0, no),
      d.diagrams(s).then((l) => l.length > 0, no),
    ]).then(([graph, tours, diagrams]) => {
      if (treeKey === key) avail = { key, graph, tours, diagrams };
    });
  });
  const tabsAvail = $derived(avail?.key === treeKey ? avail : null);

  // ---- issues.json → warnings
  let issuesRes = $state<{ key: string; issues: Issue[] } | null>(null);
  $effect(() => {
    const d = data;
    const s = sha;
    if (!d || !s) return;
    const key = treeKey;
    if (issuesRes?.key === key) return;
    d.issues(s).then(
      (i) => {
        if (treeKey === key) issuesRes = { key, issues: i?.issues ?? [] };
      },
      () => {
        if (treeKey === key) issuesRes = { key, issues: [] };
      },
    );
  });
  const issueIndex = $derived(
    issuesRes?.key === treeKey && tree ? issuesByPath(issuesRes.issues, new Set(tree.files.map((f) => f.path))) : null,
  );
  const warnings = $derived(issueIndex ? warningCounts(issueIndex) : undefined);

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
  const visibleTabs = $derived(
    TABS.filter((t) => {
      if (t.id !== 'graph' && t.id !== 'tours' && t.id !== 'diagrams') return true;
      return tab === t.id || !!tabsAvail?.[t.id];
    }),
  );
  // Last file or directory shown in the Código tab (a d/ route shows the dir there).
  let lastCode = $state<{ study: string; kind: 'file' | 'dir'; path: string; range?: LineRange } | null>(null);

  $effect(() => {
    const r = route;
    switch (r.kind) {
      case 'study':
      case 'overview':
        tab = 'overview';
        break;
      case 'file':
        tab = 'code';
        lastCode = { study: r.study, kind: 'file', path: r.path, range: r.range };
        break;
      case 'dir':
        tab = 'code';
        lastCode = { study: r.study, kind: 'dir', path: r.path };
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

  const currentCode = $derived(lastCode && lastCode.study === studyName ? lastCode : null);

  function selectTab(t: Tab) {
    if (!studyName || !sha) return;
    if (t === 'overview') navigate({ kind: 'overview', study: studyName, sha });
    else if (t === 'graph') navigate({ kind: 'graph', study: studyName, sha });
    else if (t === 'diagrams') navigate({ kind: 'diagrams', study: studyName, sha });
    else if (t === 'code' && currentCode?.kind === 'file') {
      navigate({ kind: 'file', study: studyName, sha, path: currentCode.path, range: currentCode.range });
    } else if (t === 'code' && currentCode?.kind === 'dir') {
      navigate({ kind: 'dir', study: studyName, sha, path: currentCode.path });
    } else if (t === 'tours' && route.kind === 'tour') {
      // leave the player for the list (no route for the list: stay on this hash)
      tab = 'tours';
      tourListForced = true;
    } else tab = t;
  }

  // ---- block <-> code sync
  let activeBlockId = $state<string | null>(null);
  let revealTick = $state(0);
  const codeKey = $derived(`${sha}:${currentCode?.kind}:${currentCode?.path}`);
  $effect(() => {
    // a different file (or snapshot) starts without an active block
    void codeKey;
    activeBlockId = null;
  });
  function onBlock(b: Block) {
    if (!studyName || !sha || panelTarget.kind !== 'file') return;
    const target = format({
      kind: 'file',
      study: studyName,
      sha,
      path: panelTarget.path,
      range: { start: b.range[0], end: b.range[1] },
    });
    activeBlockId = b.id;
    if (location.hash === target && tab === 'code') revealTick++;
    else location.hash = target;
  }

  // ---- tours
  let tourListForced = $state(false);
  $effect(() => {
    void route;
    tourListForced = false;
  });
  let tourRes = $state<{ key: string; tour: Tour | null; error?: string } | null>(null);
  const tourKey = $derived(route.kind === 'tour' && sha ? `${studyName}@${sha}:${route.id}` : null);
  $effect(() => {
    const key = tourKey;
    const d = data;
    const s = sha;
    const r = route;
    if (!key || !d || !s || r.kind !== 'tour') return;
    if (tourRes?.key === key) return;
    d.tour(s, r.id).then(
      (t) => {
        if (tourKey === key) tourRes = { key, tour: t };
      },
      (e: Error) => {
        if (tourKey === key) tourRes = { key, tour: null, error: e.message };
      },
    );
  });
  const tour = $derived(tourRes && tourRes.key === tourKey ? tourRes : null);
  const tourStep = $derived(
    tour?.tour && route.kind === 'tour' ? clampStep(tour.tour.steps.length, route.step) : 0,
  );
  const playing = $derived(route.kind === 'tour' && !tourListForced);
  const tourStepPath = $derived(playing && tour?.tour && tourStep > 0 ? tour.tour.steps[tourStep - 1].path : null);

  function tourGo(delta: -1 | 1) {
    if (route.kind !== 'tour' || !tour?.tour || !sha) return;
    const nav = stepNav(tour.tour.steps.length, tourStep);
    const step = delta < 0 ? nav.prev : nav.next;
    if (step !== null) navigate({ kind: 'tour', study: route.study, sha, id: route.id, step });
  }

  // ---- tree selection / right-panel target
  const treeSelected = $derived(
    route.kind === 'file'
      ? { kind: 'file' as const, path: route.path }
      : route.kind === 'dir'
        ? { kind: 'dir' as const, path: route.path }
        : route.kind === 'graph' && route.path
          ? { kind: 'file' as const, path: route.path }
          : route.kind === 'tour' && tourStepPath
            ? { kind: 'file' as const, path: tourStepPath }
            : null,
  );
  const panelTarget = $derived(treeSelected ?? { kind: 'dir' as const, path: '' });
  const panelIssues = $derived.by(() => {
    if (!issueIndex) return [];
    if (panelTarget.kind === 'file') return issueIndex.files.get(panelTarget.path) ?? [];
    const own = issueIndex.dirs.get(panelTarget.path) ?? [];
    return panelTarget.path === '' ? [...own, ...issueIndex.other] : own;
  });

  // ---- diff view
  const diffShas = $derived.by(() => {
    if (route.kind !== 'diff' || !study) return null;
    return { a: resolveSha(study, route.a), b: resolveSha(study, route.b) };
  });
  let diffRes = $state<{ key: string; changes: Changes | null; treeA: Tree | null; error?: string } | null>(null);
  const diffKey = $derived(diffShas?.a && diffShas.b ? `${studyName}:${diffShas.a}..${diffShas.b}` : null);
  $effect(() => {
    const key = diffKey;
    const d = data;
    const ab = diffShas;
    if (!key || !d || !ab?.a || !ab.b) return;
    if (diffRes?.key === key) return;
    Promise.all([d.changes(ab.a, ab.b), d.tree(ab.a).catch(() => null)]).then(
      ([changes, treeA]) => {
        if (diffKey === key) diffRes = { key, changes, treeA };
      },
      (e: Error) => {
        if (diffKey === key) diffRes = { key, changes: null, treeA: null, error: e.message };
      },
    );
  });
  const diff = $derived(diffRes && diffRes.key === diffKey ? diffRes : null);
  const diffFiles = $derived(diff?.changes ? diffTree(diff.changes, diff.treeA, tree) : null);
  const badges = $derived(diff?.changes ? diffBadges(diff.changes) : undefined);
  const diffPath = $derived(route.kind === 'diff' ? (route.path ?? null) : null);
  const diffChange = $derived(diffPath && diff?.changes ? (diff.changes.files.find((f) => f.path === diffPath) ?? null) : null);
  const diffLang = $derived.by(() => {
    const c = diffChange;
    if (!c) return null;
    const inB = tree?.files.find((f) => f.path === c.path);
    const inA = diff?.treeA?.files.find((f) => f.path === (c.oldPath ?? c.path));
    return inB?.language ?? inA?.language ?? null;
  });
  const shaFor = $derived.by(() => {
    const pathsB = tree ? new Set(tree.files.map((f) => f.path)) : null;
    const pathsA = diff?.treeA ? new Set(diff.treeA.files.map((f) => f.path)) : null;
    const a = diffShas?.a ?? '';
    const b = diffShas?.b ?? '';
    return (target: string, snapshot?: 'A' | 'B') => diffLinkSha(target, pathsB, pathsA, a, b, snapshot);
  });
  let hunkFocus = $state<{ index: number; tick: number } | null>(null);
  $effect(() => {
    void diffKey;
    void diffPath;
    hunkFocus = null;
  });
  function onHunk(index: number) {
    hunkFocus = { index, tick: (hunkFocus?.tick ?? 0) + 1 };
  }
  function exitDiff() {
    if (!studyName || !sha) return;
    if (diffPath && tree?.files.some((f) => f.path === diffPath)) navigate({ kind: 'file', study: studyName, sha, path: diffPath });
    else navigate({ kind: 'overview', study: studyName, sha });
  }

  // ---- top bar actions
  let notice = $state<string | null>(null);
  let compareOpen = $state(false);
  let searchOpen = $state(false);
  $effect(() => {
    void studyName;
    notice = null;
  });

  function onStudy(name: string) {
    navigate({ kind: 'study', study: name });
  }

  async function onSha(newSha: string) {
    if (!studyName || !data) return;
    const r = route;
    const t = await data.tree(newSha).catch(() => null);
    const res = routeOnSnapshotSwitch(r, newSha, t);
    notice = res.notice;
    navigate(res.route);
  }

  function onCompare(a: string, b: string) {
    compareOpen = false;
    if (studyName) navigate({ kind: 'diff', study: studyName, a, b });
  }

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
      if (playing && (e.key === '[' || e.key === ']')) {
        e.preventDefault();
        tourGo(e.key === '[' ? -1 : 1);
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

  // ---- resizable panes
  const panes = loadPref<{ left: number; right: number }>('panes', { left: 260, right: 380 });
  let leftW = $state(Number(panes.left) || 260);
  let rightW = $state(Number(panes.right) || 380);
  const clamp = (w: number) => Math.max(150, Math.min(w, window.innerWidth * 0.6));
  const savePanes = () => savePref('panes', { left: leftW, right: rightW });

  const graphHref = $derived(
    tabsAvail?.graph && studyName && sha && currentCode?.kind === 'file'
      ? format({ kind: 'graph', study: studyName, sha, path: currentCode.path })
      : null,
  );
  const ready = $derived(!!study && study.schemaVersion === 1 && !!sha && !!data);
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
    onCompare={ready ? () => (compareOpen = true) : null}
    onSearch={ready && tree ? () => (searchOpen = true) : null}
    diffLabel={diffShas?.a && diffShas.b ? `${diffShas.a.slice(0, 7)} → ${diffShas.b.slice(0, 7)}` : null}
  />
  {#if notice}
    <div class="notice" role="status">
      <span>{notice}</span>
      <button aria-label="Cerrar aviso" onclick={() => (notice = null)}>✕</button>
    </div>
  {/if}

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
    <div class="empty full">Este estudio usa un formato no compatible (schemaVersion {study.schemaVersion}).</div>
  {:else if study.snapshots.length === 0}
    <div class="empty full">
      El estudio <code>{study.name}</code> todavía no tiene commits estudiados. Ejecuta <code>/readcode study</code> para generar
      el primero.
    </div>
  {:else if !sha}
    <div class="empty">Commit no encontrado en el estudio: {routeSha(route)}.</div>
  {:else if data}
    <div class="panes">
      <aside class="pane" style="width: {leftW}px">
        {#if route.kind === 'diff'}
          {#if diffFiles}
            <FileTree
              tree={diffFiles}
              selected={diffPath ? { kind: 'file', path: diffPath } : null}
              {badges}
              diffMode
              onFile={(path) => navigate({ kind: 'diff', study: study.name, a: route.kind === 'diff' ? route.a : '', b: sha, path })}
              onDir={() => {}}
            />
          {:else}
            <div class="empty">{diff ? 'Sin cambios que mostrar.' : 'Cargando…'}</div>
          {/if}
        {:else if tree}
          <FileTree
            {tree}
            selected={treeSelected}
            {warnings}
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
        {#if route.kind === 'diff'}
          <div class="tabs diffbar">
            <span>Comparando <code>{route.a.slice(0, 7)}</code> → <code>{route.b.slice(0, 7)}</code></span>
            <button onclick={exitDiff}>salir de la comparación</button>
          </div>
          <div class="tab-body">
            {#if !diffShas?.a}
              <div class="empty">Commit A no encontrado en el estudio: {route.a}.</div>
            {:else if !diff}
              <div class="empty">Cargando…</div>
            {:else if diff.error}
              <div class="empty">Error al cargar el diff: {diff.error}</div>
            {:else if !diff.changes}
              <div class="empty">
                sin diff generado — ejecuta <code>/readcode diff {study.name} {route.a.slice(0, 7)} {route.b.slice(0, 7)}</code>
              </div>
            {:else if !diffPath}
              <div class="empty">
                Selecciona un archivo del árbol para ver sus cambios lado a lado.
                <ul class="changed">
                  {#each diff.changes.files as f (f.path)}
                    {@const bd = badges?.get(f.path)}
                    <li>
                      <span class="badge diff-{bd?.badge}" title={bd?.title}>{bd?.badge}</span>
                      <a href={format({ kind: 'diff', study: study.name, a: route.a, b: route.b, path: f.path })}>{f.path}</a>
                    </li>
                  {/each}
                </ul>
              </div>
            {:else if !diffChange}
              <div class="empty">«{diffPath}» no cambió entre estos commits.</div>
            {:else}
              <DiffView
                {data}
                a={diffShas.a}
                b={sha}
                change={diffChange}
                badge={badges?.get(diffChange.path)}
                language={diffLang}
                focus={hunkFocus}
              />
            {/if}
          </div>
        {:else}
          <div class="tabs" role="tablist">
            {#each visibleTabs as t (t.id)}
              <button role="tab" class:active={tab === t.id} aria-selected={tab === t.id} onclick={() => selectTab(t.id)}>
                {t.label}
              </button>
            {/each}
          </div>
          <div class="tab-body">
            {#if tab === 'overview'}
              <OverviewView {data} study={study.name} {sha} />
            {:else if tab === 'diagrams'}
              <DiagramsView {data} study={study.name} {sha} name={route.kind === 'diagrams' ? route.name : undefined} />
            {:else if tab === 'graph'}
              {#if tree}
                <GraphView {data} study={study.name} {sha} {tree} focus={route.kind === 'graph' ? route.path : undefined} />
              {:else}
                <div class="empty">Cargando…</div>
              {/if}
            {:else if tab === 'tours'}
              {#if playing}
                {#if !tour}
                  <div class="empty">Cargando tour…</div>
                {:else if tour.error}
                  <div class="empty">Error al cargar el tour: {tour.error}</div>
                {:else if !tour.tour || tour.tour.steps.length === 0}
                  <div class="empty">
                    El tour <code>{route.kind === 'tour' ? route.id : ''}</code> no existe en este commit.
                    <button onclick={() => (tourListForced = true)}>Ver tours</button>
                  </div>
                {:else if tree}
                  {@const step = tour.tour.steps[tourStep - 1]}
                  <CodeView
                    {data}
                    study={study.name}
                    {sha}
                    {tree}
                    path={step.path}
                    range={{ start: step.range[0], end: step.range[1] }}
                    activeId={null}
                    revealTick={0}
                    onActive={() => {}}
                  />
                {/if}
              {:else}
                <!-- the list has no route: opening the tour already in the hash causes no hashchange -->
                <ToursView {data} study={study.name} {sha} onStart={() => (tourListForced = false)} />
              {/if}
            {:else if tab === 'code'}
              {#if currentCode?.kind === 'dir' && tree}
                <DirView {data} study={study.name} {sha} {tree} path={currentCode.path} />
              {:else if currentCode?.kind === 'file' && tree}
                <CodeView
                  {data}
                  study={study.name}
                  {sha}
                  {tree}
                  path={currentCode.path}
                  range={currentCode.range}
                  activeId={activeBlockId}
                  {revealTick}
                  onActive={(id) => (activeBlockId = id)}
                  {graphHref}
                />
              {:else}
                <div class="empty">Selecciona un archivo en el árbol.</div>
              {/if}
            {/if}
          </div>
        {/if}
      </main>
      <Splitter onDrag={(dx) => (rightW = clamp(rightW - dx))} onEnd={savePanes} />
      <aside class="pane" style="width: {rightW}px">
        {#if route.kind === 'diff'}
          {#if diff?.changes && diffShas?.a}
            <DiffPanel
              {data}
              study={study.name}
              a={diffShas.a}
              b={sha}
              changes={diff.changes}
              change={diffChange}
              badge={diffChange ? badges?.get(diffChange.path) : undefined}
              {shaFor}
              activeHunk={hunkFocus?.index ?? null}
              {onHunk}
            />
          {/if}
        {:else if tab === 'tours' && playing && tour?.tour && tourStep > 0}
          <TourPanel {data} study={study.name} {sha} tour={tour.tour} step={tourStep} />
        {:else}
          <ExplainPanel
            {data}
            study={study.name}
            {sha}
            {tree}
            target={panelTarget}
            showChildren={!(tab === 'code' && route.kind === 'dir')}
            activeId={panelTarget.kind === 'file' && tab === 'code' ? activeBlockId : null}
            {onBlock}
            issues={panelIssues}
          />
        {/if}
      </aside>
    </div>
    {#if compareOpen && study}
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
  .full {
    margin: 3rem auto;
    max-width: 40rem;
    font-size: 15px;
    text-align: center;
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
  .diffbar {
    align-items: center;
    justify-content: space-between;
    padding: 4px 10px;
    font-size: 13px;
  }
  .diffbar button {
    border: 1px solid var(--border);
    border-radius: 4px;
    padding: 2px 8px;
    margin-bottom: 4px;
  }
  .tab-body {
    flex: 1;
    min-height: 0;
    overflow: hidden;
  }
  .changed {
    list-style: none;
    padding: 0;
    margin: 12px 0 0;
  }
  .changed li {
    padding: 3px 0;
    font-family: var(--font-code);
    font-size: 13px;
  }
  .badge {
    display: inline-block;
    width: 1.5em;
    text-align: center;
    font-size: 10px;
    font-weight: 700;
    border-radius: 8px;
    color: var(--accent-fg);
    margin-right: 6px;
  }
  .diff-A {
    background: var(--added);
  }
  .diff-M {
    background: var(--warn);
  }
  .diff-D {
    background: var(--danger);
  }
  .diff-R {
    background: var(--accent);
  }
</style>
