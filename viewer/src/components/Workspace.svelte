<script lang="ts">
  // Three-pane workspace of a study at one snapshot: file tree | center tabs
  // (code, graph, diagrams, overview, tours) or the diff view | explanation panel.
  import CodeView from './CodeView.svelte';
  import DiagramsView from './DiagramsView.svelte';
  import DiffPanel from './DiffPanel.svelte';
  import DiffView from './DiffView.svelte';
  import DirView from './DirView.svelte';
  import ExplainPanel from './ExplainPanel.svelte';
  import FileTree from './FileTree.svelte';
  import GraphView from './GraphView.svelte';
  import OverviewView from './OverviewView.svelte';
  import Splitter from './Splitter.svelte';
  import TourPanel from './TourPanel.svelte';
  import ToursView from './ToursView.svelte';
  import type { StudyData } from '../lib/data';
  import { diffBadges, diffLinkSha, diffTree } from '../lib/diff';
  import type { CodeLocation, Nav } from '../lib/nav';
  import { loadPref, savePref } from '../lib/prefs';
  import { format, resolveSha, type Route } from '../lib/router';
  import { clampStep, stepNav } from '../lib/tours';
  import type { Block, Changes, Issue, Study, Tour, Tree } from '../lib/types';
  import { issuesByPath, warningCounts } from '../lib/warnings';

  interface Props {
    nav: Nav;
    route: Route;
    data: StudyData;
    studyName: string;
    study: Study;
    sha: string;
    /** tree.json of this snapshot once its load finished (value null: the file is missing). */
    treeLoad: { value: Tree | null; error: string | null } | null;
    lastCode: CodeLocation | null;
    /** Out: steps the playing tour (null when no tour is playing). */
    stepTour?: ((delta: -1 | 1) => void) | null;
  }

  let { nav, route, data, studyName, study, sha, treeLoad, lastCode, stepTour = $bindable(null) }: Props = $props();

  const tree = $derived(treeLoad?.value ?? null);
  const treeKey = $derived(`${studyName}@${sha}`);

  // ---- data-dependent tabs (hidden when their data is missing)
  let avail = $state<{ key: string; graph: boolean; tours: boolean; diagrams: boolean } | null>(null);
  $effect(() => {
    const d = data;
    const s = sha;
    const st = study;
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

  $effect(() => {
    switch (route.kind) {
      case 'study':
      case 'overview':
        tab = 'overview';
        break;
      case 'file':
      case 'dir':
        tab = 'code';
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
    if (t === 'overview') nav.go({ kind: 'overview', study: studyName, sha });
    else if (t === 'graph') nav.go({ kind: 'graph', study: studyName, sha });
    else if (t === 'diagrams') nav.go({ kind: 'diagrams', study: studyName, sha });
    else if (t === 'code' && currentCode?.kind === 'file') {
      nav.go({ kind: 'file', study: studyName, sha, path: currentCode.path, range: currentCode.range });
    } else if (t === 'code' && currentCode?.kind === 'dir') {
      nav.go({ kind: 'dir', study: studyName, sha, path: currentCode.path });
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
    if (panelTarget.kind !== 'file') return;
    activeBlockId = b.id;
    const range = { start: b.range[0], end: b.range[1] };
    const moved = nav.go({ kind: 'file', study: studyName, sha, path: panelTarget.path, range });
    if (!moved && tab === 'code') revealTick++;
  }

  // ---- tours
  let tourListForced = $state(false);
  $effect(() => {
    void route;
    tourListForced = false;
  });
  let tourRes = $state<{ key: string; tour: Tour | null; error?: string } | null>(null);
  const tourKey = $derived(route.kind === 'tour' ? `${studyName}@${sha}:${route.id}` : null);
  $effect(() => {
    const key = tourKey;
    const d = data;
    const s = sha;
    const r = route;
    if (!key || r.kind !== 'tour') return;
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
    if (route.kind !== 'tour' || !tour?.tour) return;
    const steps = stepNav(tour.tour.steps.length, tourStep);
    const step = delta < 0 ? steps.prev : steps.next;
    if (step !== null) nav.go({ kind: 'tour', study: route.study, sha, id: route.id, step });
  }
  $effect(() => {
    stepTour = playing ? tourGo : null;
  });

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
  const diffShas = $derived(route.kind === 'diff' ? { a: resolveSha(study, route.a), b: resolveSha(study, route.b) } : null);
  let diffRes = $state<{ key: string; changes: Changes | null; treeA: Tree | null; error?: string } | null>(null);
  const diffKey = $derived(diffShas?.a && diffShas.b ? `${studyName}:${diffShas.a}..${diffShas.b}` : null);
  $effect(() => {
    const key = diffKey;
    const d = data;
    const ab = diffShas;
    if (!key || !ab?.a || !ab.b) return;
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
    if (diffPath && tree?.files.some((f) => f.path === diffPath)) nav.go({ kind: 'file', study: studyName, sha, path: diffPath });
    else nav.go({ kind: 'overview', study: studyName, sha });
  }

  // ---- resizable panes
  const panes = loadPref<{ left: number; right: number }>('panes', { left: 260, right: 380 });
  let leftW = $state(Number(panes.left) || 260);
  let rightW = $state(Number(panes.right) || 380);
  const clamp = (w: number) => Math.max(150, Math.min(w, window.innerWidth * 0.6));
  const savePanes = () => savePref('panes', { left: leftW, right: rightW });

  const graphHref = $derived(
    tabsAvail?.graph && currentCode?.kind === 'file'
      ? format({ kind: 'graph', study: studyName, sha, path: currentCode.path })
      : null,
  );
</script>

<div class="panes">
  <aside class="pane" style="width: {leftW}px">
    {#if route.kind === 'diff'}
      {#if diffFiles}
        <FileTree
          tree={diffFiles}
          selected={diffPath ? { kind: 'file', path: diffPath } : null}
          {badges}
          diffMode
          onFile={(path) => nav.go({ kind: 'diff', study: study.name, a: route.kind === 'diff' ? route.a : '', b: sha, path })}
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
        onFile={(path) => nav.go({ kind: 'file', study: study.name, sha, path })}
        onDir={(path) => nav.go({ kind: 'dir', study: study.name, sha, path })}
      />
    {:else if treeLoad?.error}
      <div class="empty">Error al cargar tree.json: {treeLoad.error}</div>
    {:else if treeLoad}
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

<style>
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
