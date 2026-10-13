<script lang="ts">
  // Right pane: directory summary or file explanation (basic; Task 10 adds
  // markers, block sync and diagrams).
  import type { StudyData } from '../lib/data';
  import { format } from '../lib/router';
  import Markdown from './Markdown.svelte';

  interface Props {
    data: StudyData;
    study: string;
    sha: string;
    target: { kind: 'file' | 'dir'; path: string } | null;
  }

  let { data, study, sha, target }: Props = $props();

  const dir = $derived(target?.kind === 'dir' ? data.dir(sha, target.path) : null);
  const explain = $derived(target?.kind === 'file' ? data.explain(sha, target.path) : null);

  function name(path: string): string {
    return path.slice(path.lastIndexOf('/') + 1);
  }
</script>

<div class="panel">
  {#if !target}
    <div class="empty">Selecciona un archivo o directorio para ver su explicación.</div>
  {:else if target.kind === 'dir'}
    <h2>{target.path === '' ? 'Raíz del repositorio' : target.path + '/'}</h2>
    {#await dir}
      <div class="empty">Cargando…</div>
    {:then d}
      {#if !d}
        <div class="empty">Sin resumen para este directorio.</div>
      {:else}
        <Markdown source={d.summary} />
        {#if d.children.length > 0}
          <h3>Contenido</h3>
          <ul class="children">
            {#each d.children as c (c.path)}
              <li>
                <a href={format(c.kind === 'dir' ? { kind: 'dir', study, sha, path: c.path } : { kind: 'file', study, sha, path: c.path })}
                  >{name(c.path)}{c.kind === 'dir' ? '/' : ''}</a
                >
                <span class="one-line">{c.oneLine}</span>
              </li>
            {/each}
          </ul>
        {/if}
      {/if}
    {:catch err}
      <div class="empty">Error: {err.message}</div>
    {/await}
  {:else}
    <h2>{name(target.path)}</h2>
    {#await explain}
      <div class="empty">Cargando…</div>
    {:then e}
      {#if !e}
        <div class="empty">Sin explicación para este archivo.</div>
      {:else}
        <Markdown source={e.summary} />
        {#each e.blocks as b (b.id)}
          <section class="block">
            <h3>
              <a href={format({ kind: 'file', study, sha, path: target.path, range: { start: b.range[0], end: b.range[1] } })}
                >{b.title}</a
              >
              <span class="range">L{b.range[0]}–{b.range[1]}</span>
            </h3>
            <Markdown source={b.body} />
          </section>
        {/each}
      {/if}
    {:catch err}
      <div class="empty">Error: {err.message}</div>
    {/await}
  {/if}
</div>

<style>
  .panel {
    padding: 8px 14px;
    overflow: auto;
    height: 100%;
  }
  h2 {
    font-size: 15px;
    font-family: var(--font-code);
    margin: 6px 0 10px;
    overflow-wrap: anywhere;
  }
  h3 {
    font-size: 14px;
    margin: 14px 0 4px;
  }
  .children {
    list-style: none;
    padding: 0;
  }
  .children li {
    padding: 3px 0;
  }
  .children a {
    font-family: var(--font-code);
  }
  .one-line {
    color: var(--fg-muted);
    margin-left: 6px;
  }
  .block {
    border-top: 1px solid var(--border);
    margin-top: 10px;
  }
  .range {
    color: var(--fg-muted);
    font-weight: normal;
    font-size: 12px;
    margin-left: 6px;
  }
</style>
