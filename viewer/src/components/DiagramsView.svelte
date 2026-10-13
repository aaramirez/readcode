<script lang="ts">
  // Diagrams tab: diagrams of the snapshot (from links.json). The selected one
  // (route diagrams/<key>) is an archify page in a large sandboxed iframe, or a
  // mermaid source (.mmd) rendered inline. A mermaid entry's route key is "<name>.mmd",
  // so an archify and a mermaid diagram with the same name stay distinct.
  import type { StudyData } from '../lib/data';
  import type { DiagramEntry } from '../lib/types';
  import { format } from '../lib/router';
  import MermaidDiagram from './MermaidDiagram.svelte';

  let { data, study, sha, name }: { data: StudyData; study: string; sha: string; name?: string } = $props();

  const list = $derived(data.diagrams(sha));
  const keyOf = (e: DiagramEntry) => (e.kind === 'mermaid' ? `${e.name}.mmd` : e.name);
</script>

<div class="diagrams">
  {#await list}
    <div class="empty">Cargando…</div>
  {:then entries}
    {#if entries.length === 0}
      <div class="empty">Este commit no tiene diagramas. Los bloques Mermaid de las explicaciones se muestran dentro de ellas.</div>
    {:else}
      {@const selected = entries.find((e) => keyOf(e) === name)}
      <nav class="list" aria-label="Diagramas">
        {#each entries as e (keyOf(e))}
          <a
            href={format({ kind: 'diagrams', study, sha, name: keyOf(e) })}
            class:selected={keyOf(e) === name}
            class:broken={e.broken}
            title={e.broken ? 'Diagrama roto: no existe diagrams/' + e.name + '.html' : e.name}
            >{e.name}{#if e.kind === 'mermaid'}<span class="badge kind">mmd</span>{/if}{#if e.broken}<span class="badge">roto</span>{/if}</a
          >
        {/each}
      </nav>
      <div class="stage">
        {#if !name}
          <div class="empty">Selecciona un diagrama.</div>
        {:else if !selected}
          <div class="empty">El diagrama <code>{name}</code> no está referenciado en este commit.</div>
        {:else if selected.kind === 'mermaid'}
          <div class="toolbar"><strong>{selected.name}</strong></div>
          {#key selected.name}
            <MermaidDiagram {data} {sha} name={selected.name} />
          {/key}
        {:else if selected.broken || !data.diagramUrl(sha, selected.name)}
          <div class="error">
            El diagrama <code>{name}</code> está referenciado pero no existe <code>diagrams/{name}.html</code> en este commit
            (marcador <code>[[archify:{name}]]</code> roto).
          </div>
        {:else}
          {@const url = data.diagramUrl(sha, selected.name) ?? ''}
          <div class="toolbar">
            <strong>{selected.name}</strong>
            <a href={url} target="_blank" rel="noopener">abrir en pestaña</a>
          </div>
          {#key url}
            <iframe sandbox="allow-scripts" src={url} title="Diagrama {selected.name}"></iframe>
          {/key}
        {/if}
      </div>
    {/if}
  {:catch err}
    <div class="empty">Error al cargar links.json: {err.message}</div>
  {/await}
</div>

<style>
  .diagrams {
    display: flex;
    height: 100%;
    min-height: 0;
  }
  .list {
    flex: none;
    width: 180px;
    border-right: 1px solid var(--border);
    overflow: auto;
    padding: 6px 0;
  }
  .list a {
    display: flex;
    justify-content: space-between;
    gap: 6px;
    padding: 4px 10px;
    color: var(--fg);
    text-decoration: none;
    font-family: var(--font-code);
    font-size: 13px;
    overflow-wrap: anywhere;
  }
  .list a:hover {
    background: var(--bg-hover);
  }
  .list a.selected {
    background: var(--bg-selected);
  }
  .list a.broken {
    color: var(--fg-muted);
  }
  .badge {
    font-family: var(--font-ui);
    font-size: 11px;
    color: var(--danger);
  }
  .badge.kind {
    color: var(--fg-muted);
  }
  .stage {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
  }
  .toolbar {
    display: flex;
    gap: 12px;
    align-items: baseline;
    padding: 6px 10px;
    border-bottom: 1px solid var(--border);
  }
  iframe {
    flex: 1;
    width: 100%;
    border: 0;
    background: var(--bg);
  }
  .error {
    margin: 16px;
    padding: 10px 12px;
    border: 1px solid var(--danger);
    border-radius: 6px;
    color: var(--fg);
  }
</style>
