<script lang="ts">
  // Plain read-only file view with line numbers (Task 10 replaces it with CodeMirror).
  import { tick } from 'svelte';
  import type { StudyData } from '../lib/data';
  import type { LineRange } from '../lib/router';
  import type { Tree } from '../lib/types';

  interface Props {
    data: StudyData;
    tree: Tree;
    path: string;
    range?: LineRange;
  }

  let { data, tree, path, range }: Props = $props();

  const file = $derived(tree.files.find((f) => f.path === path));
  const excluded = $derived(tree.excluded.find((e) => e.path === path));
  const content = $derived(file ? data.blob(file.blob) : null);
  let pre: HTMLElement | undefined = $state();

  function lines(text: string): string[] {
    const ls = text.split(/\r?\n/);
    if (ls.length > 1 && ls[ls.length - 1] === '') ls.pop();
    return ls;
  }

  function inRange(n: number): boolean {
    if (!range) return false;
    return n >= range.start && n <= (range.end ?? range.start);
  }

  // Scroll the highlighted range into view once the content is rendered.
  $effect(() => {
    const r = range;
    const p = content;
    if (!r || !p) return;
    p.then(() => tick()).then(() => {
      pre?.querySelector(`[data-line="${r.start}"]`)?.scrollIntoView({ block: 'center' });
    });
  });

  const REASONS: Record<string, string> = {
    gitignore: '.gitignore',
    default: 'exclusiones por defecto',
    study: 'reglas del estudio',
    binary: 'archivo binario',
    size: 'tamaño mayor a 1 MB',
  };
</script>

<div class="code">
  <div class="header">
    <span class="path">{path}</span>
    {#if file}<span class="meta">{file.language ?? 'texto'} · {file.lines} líneas</span>{/if}
  </div>
  {#if excluded}
    <div class="empty">Archivo excluido del estudio ({REASONS[excluded.reason] ?? excluded.reason}).</div>
  {:else if !file}
    <div class="empty">El archivo no existe en este commit.</div>
  {:else}
    {#await content}
      <div class="empty">Cargando…</div>
    {:then text}
      {#if text === null || text === undefined}
        <div class="empty">No se encontró el contenido del archivo.</div>
      {:else}
        <pre bind:this={pre}>{#each lines(text) as line, i (i)}<span class="line" class:hl={inRange(i + 1)} data-line={i + 1}><span class="ln">{i + 1}</span>{line}</span>{/each}</pre>
      {/if}
    {:catch err}
      <div class="empty">Error al cargar el archivo: {err.message}</div>
    {/await}
  {/if}
</div>

<style>
  .code {
    display: flex;
    flex-direction: column;
    height: 100%;
    min-height: 0;
  }
  .header {
    display: flex;
    gap: 12px;
    align-items: baseline;
    padding: 6px 10px;
    border-bottom: 1px solid var(--border);
    font-family: var(--font-code);
    font-size: 12px;
  }
  .meta {
    color: var(--fg-muted);
  }
  pre {
    margin: 0;
    flex: 1;
    overflow: auto;
    font-family: var(--font-code);
    font-size: 13px;
    line-height: 1.5;
    background: var(--code-bg);
    padding: 4px 0;
  }
  .line {
    display: block;
    min-height: 1.5em;
    padding-right: 12px;
  }
  .line.hl {
    background: var(--bg-highlight);
  }
  .ln {
    display: inline-block;
    width: 4.5em;
    padding-right: 1em;
    text-align: right;
    color: var(--fg-faint);
    user-select: none;
  }
</style>
