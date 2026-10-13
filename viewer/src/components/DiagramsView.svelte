<script lang="ts">
  // Diagrams tab: archify diagrams referenced by the snapshot (from links.json);
  // the selected one (route diagrams/<name>) is shown in a large sandboxed iframe.
  import type { StudyData } from '../lib/data';
  import { format } from '../lib/router';

  let { data, study, sha, name }: { data: StudyData; study: string; sha: string; name?: string } = $props();

  const list = $derived(data.diagrams(sha));
</script>

<div class="diagrams">
  {#await list}
    <div class="empty">Cargando…</div>
  {:then entries}
    {#if entries.length === 0}
      <div class="empty">Este commit no tiene diagramas de Archify. Los diagramas Mermaid aparecen dentro de las explicaciones.</div>
    {:else}
      {@const selected = entries.find((e) => e.name === name)}
      <nav class="list" aria-label="Diagramas">
        {#each entries as e (e.name)}
          <a
            href={format({ kind: 'diagrams', study, sha, name: e.name })}
            class:selected={e.name === name}
            class:broken={e.broken}
            title={e.broken ? 'Diagrama roto: no existe diagrams/' + e.name + '.html' : e.name}
            >{e.name}{#if e.broken}<span class="badge">roto</span>{/if}</a
          >
        {/each}
      </nav>
      <div class="stage">
        {#if !name}
          <div class="empty">Selecciona un diagrama.</div>
        {:else if !selected}
          <div class="empty">El diagrama <code>{name}</code> no está referenciado en este commit.</div>
        {:else if selected.broken}
          <div class="error">
            El diagrama <code>{name}</code> está referenciado pero no existe <code>diagrams/{name}.html</code> en este commit
            (marcador <code>[[archify:{name}]]</code> roto).
          </div>
        {:else}
          {@const url = data.diagramUrl(sha, selected.name)}
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
