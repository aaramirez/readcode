<script lang="ts">
  import Shell from './components/Shell.svelte';
  import StudyList from './components/StudyList.svelte';
  import Workspace from './components/Workspace.svelte';
  import { KbClient } from './lib/data';
  import { createNav } from './lib/nav';
  import { latestSnapshot, resolveSha, routeSha, routeStudy } from './lib/router';
  import type { Catalog, Study, Tree } from './lib/types';

  const kb = new KbClient('kb/');

  // ---- routing (hash ↔ route, ← → history)
  const nav = createNav();
  const route = $derived($nav.route);

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
  const treeLoad = $derived(treeRes && treeRes.key === `${studyName}@${sha}` ? treeRes : null);
  const tree = $derived(treeLoad?.value ?? null);

  // The workspace is shown exactly when ready (see the chain below).
  const ready = $derived(!!study && study.schemaVersion === 1 && !!sha && !!data);
  let stepTour = $state<((delta: -1 | 1) => void) | null>(null);
</script>

<Shell {nav} {route} {catalog} {studyName} {study} {sha} {tree} {data} {ready} stepTour={ready ? stepTour : null}>
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
  {:else if data && studyName}
    <Workspace {nav} {route} {data} {studyName} {study} {sha} {treeLoad} lastCode={$nav.lastCode} bind:stepTour />
  {/if}
</Shell>

<style>
  .full {
    margin: 3rem auto;
    max-width: 40rem;
    font-size: 15px;
    text-align: center;
  }
</style>
