<script lang="ts">
  // Right pane: file explanation (summary + block cards synced with the code)
  // or a directory summary.
  import { tick } from 'svelte';
  import type { StudyData } from '../lib/data';
  import { format } from '../lib/router';
  import type { Block, Issue, Tree } from '../lib/types';
  import Markdown from './Markdown.svelte';

  interface Props {
    data: StudyData;
    study: string;
    sha: string;
    tree: Tree | null;
    target: { kind: 'file' | 'dir'; path: string } | null;
    /** List the directory's children (off when the center already shows them). */
    showChildren?: boolean;
    activeId: string | null;
    onBlock: (block: Block) => void;
    /** issues.json problems of the target (shown as a warning banner). */
    issues?: Issue[];
  }

  let { data, study, sha, tree, target, showChildren = true, activeId, onBlock, issues = [] }: Props = $props();

  const SOURCES: Record<Issue['source'], string> = { validate: 'validate', generator: 'generador', tool: 'herramienta' };

  const dir = $derived(target?.kind === 'dir' ? data.dir(sha, target.path) : null);
  const explain = $derived(target?.kind === 'file' ? data.explain(sha, target.path) : null);
  const treeFile = $derived(target?.kind === 'file' ? tree?.files.find((f) => f.path === target.path) : undefined);
  const excluded = $derived(target?.kind === 'file' ? tree?.excluded.find((e) => e.path === target.path) : undefined);

  const REASONS: Record<string, string> = {
    gitignore: 'está ignorado por .gitignore',
    default: 'coincide con las exclusiones por defecto',
    study: 'coincide con las exclusiones del estudio',
    binary: 'es un archivo binario',
    size: 'pesa más de 1 MB',
  };

  function name(path: string): string {
    return path.slice(path.lastIndexOf('/') + 1);
  }

  function blockHref(path: string, b: Block): string {
    return format({ kind: 'file', study, sha, path, range: { start: b.range[0], end: b.range[1] } });
  }

  // Keep the active card in view (scroll the panel only, never the page).
  let panel: HTMLElement | undefined = $state();
  $effect(() => {
    const id = activeId;
    const p = panel;
    const ex = explain;
    if (!id || !p || !ex) return;
    // The cards exist only once the explanation has loaded and rendered.
    let cancelled = false;
    ex.then(() => tick()).then(
      () => {
        if (cancelled) return;
        const card = p.querySelector<HTMLElement>(`[data-block="${CSS.escape(id)}"]`);
        if (!card) return;
        const pr = p.getBoundingClientRect();
        const cr = card.getBoundingClientRect();
        if (cr.top < pr.top || cr.top > pr.bottom - 48) {
          p.scrollTo({ top: p.scrollTop + cr.top - pr.top - 8, behavior: 'smooth' });
        }
      },
      () => {},
    );
    return () => {
      cancelled = true;
    };
  });

  function cardClick(e: MouseEvent, b: Block) {
    const t = e.target as Element;
    if (t.closest('a, button, iframe, input, select, .rc-mermaid')) return;
    if (window.getSelection()?.toString()) return; // the user is selecting text
    onBlock(b);
  }

  function headerClick(e: MouseEvent, b: Block) {
    if (e.button !== 0 || e.ctrlKey || e.metaKey || e.shiftKey || e.altKey) return;
    e.preventDefault();
    onBlock(b);
  }
</script>

<div class="panel" data-testid="explain-panel" bind:this={panel}>
  {#if !target}
    <div class="empty">Selecciona un archivo o directorio para ver su explicación.</div>
  {:else if target.kind === 'dir'}
    <h2>{target.path === '' ? 'Raíz del repositorio' : target.path + '/'}</h2>
    {@render warningBanner()}
    {#await dir}
      <div class="empty">Cargando…</div>
    {:then d}
      {#if !d}
        <div class="empty">Sin resumen para este directorio.</div>
      {:else}
        <Markdown
          source={d.summary}
          doc={{ data, study, sha, docKey: `dirs/${target.path === '' ? '_root' : target.path}.json` }}
        />
        {#if showChildren && d.children.length > 0}
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
    {@const path = target.path}
    <h2>{name(path)}</h2>
    {@render warningBanner()}
    {#await explain}
      <div class="empty">Cargando…</div>
    {:then e}
      {#if !e}
        <div class="empty">
          <strong>Este archivo no tiene explicación.</strong>
          {#if excluded}
            <p>Está excluido del estudio: {REASONS[excluded.reason] ?? excluded.reason}.</p>
          {:else if !treeFile}
            <p>El archivo no existe en este commit.</p>
          {:else if !treeFile.indexed}
            <p>No está indexado ({treeFile.language ? `lenguaje «${treeFile.language}» sin análisis de símbolos` : 'tipo de archivo no reconocido'}) y no se generó explicación para él.</p>
          {:else}
            <p>Todavía no se generó su explicación en este commit.</p>
          {/if}
        </div>
      {:else}
        {@const doc = { data, study, sha, docKey: `explain/${path}.json` }}
        <div class="summary"><Markdown source={e.summary} {doc} /></div>
        {#each e.blocks as b (b.id)}
          <!-- svelte-ignore a11y_click_events_have_key_events, a11y_no_static_element_interactions -->
          <section class="card" class:active={b.id === activeId} data-block={b.id} onclick={(ev) => cardClick(ev, b)}>
            <header>
              <a class="title" href={blockHref(path, b)} onclick={(ev) => headerClick(ev, b)}>{b.title}</a>
              <span class="chip">L{b.range[0]}–{b.range[1]}</span>
            </header>
            <Markdown source={b.body} {doc} />
          </section>
        {/each}
      {/if}
    {:catch err}
      <div class="empty">Error: {err.message}</div>
    {/await}
  {/if}
</div>

{#snippet warningBanner()}
  {#if issues.length > 0}
    <div class="warnings" role="alert">
      <strong>⚠ {issues.length === 1 ? '1 problema reportado' : `${issues.length} problemas reportados`}</strong>
      <ul>
        {#each issues as i, n (n)}
          <li>
            {i.problem}
            {#if i.hint}<span class="hint">— {i.hint}</span>{/if}
            <span class="source">({SOURCES[i.source] ?? i.source}{i.file ? ` · ${i.file}` : ''})</span>
          </li>
        {/each}
      </ul>
    </div>
  {/if}
{/snippet}

<style>
  .warnings {
    border: 1px solid var(--warn);
    border-left-width: 4px;
    border-radius: 6px;
    padding: 6px 10px;
    margin: 0 0 12px;
    font-size: 13px;
  }
  .warnings ul {
    margin: 4px 0 0;
    padding-left: 18px;
  }
  .warnings .hint,
  .warnings .source {
    color: var(--fg-muted);
  }
  .panel {
    padding: 8px 12px 40px;
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
  .summary {
    margin-bottom: 12px;
  }
  .card {
    border: 1px solid var(--border);
    border-left: 3px solid var(--border);
    border-radius: 6px;
    padding: 8px 12px 4px;
    margin: 10px 0;
    cursor: pointer;
    background: var(--bg);
  }
  .card:hover {
    border-left-color: var(--fg-faint);
  }
  .card.active {
    border-left-color: var(--accent);
    background: var(--bg-block);
  }
  .card header {
    display: flex;
    align-items: baseline;
    gap: 8px;
  }
  .title {
    font-weight: 600;
    color: var(--fg);
    text-decoration: none;
    flex: 1;
  }
  .title:hover {
    text-decoration: underline;
  }
  .chip {
    font-family: var(--font-code);
    font-size: 11px;
    background: var(--badge-bg);
    color: var(--fg-muted);
    border-radius: 10px;
    padding: 1px 8px;
    white-space: nowrap;
  }
  .empty p {
    margin: 6px 0 0;
  }
</style>
