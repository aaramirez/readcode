<script lang="ts">
  // Right pane of the diff view: the global explanation (explain.md) when no
  // file is selected, else that file's diff explanation (summary + one card per
  // changes.json hunk with its diff-explain body). Clicking a card reveals the hunk.
  // Markers resolve against diffs/<a>..<b>/links.json (sha = B; targets missing
  // from B open in A — ruling 16).
  import type { StudyData } from '../lib/data';
  import type { DiffBadge } from '../lib/diff';
  import type { ChangedFile, Changes, Hunk } from '../lib/types';
  import Markdown, { type MdDoc } from './Markdown.svelte';

  interface Props {
    data: StudyData;
    study: string;
    a: string;
    b: string;
    changes: Changes;
    change: ChangedFile | null;
    badge?: DiffBadge;
    shaFor: (target: string, snapshot?: 'A' | 'B') => string;
    activeHunk: number | null;
    onHunk: (index: number) => void;
  }

  let { data, study, a, b, changes, change, badge, shaFor, activeHunk, onHunk }: Props = $props();

  const links = $derived(data.diffLinks(a, b));
  const global = $derived(change ? null : data.diffExplain(a, b));
  const fileExplain = $derived(change ? data.diffFileExplain(a, b, change.path) : null);

  function doc(docKey: string): MdDoc {
    return { data, study, sha: b, docKey, links, scope: `diff:${a}..${b}`, shaFor };
  }

  function hunkLabel(h: Hunk, i: number): string {
    if (h.header) return h.header;
    const r = (x: [number, number] | null) => (x ? `${x[0]}–${x[1]}` : '—');
    return `hunk ${i + 1}: A ${r(h.fromRange)} → B ${r(h.toRange)}`;
  }

  const counts = $derived.by(() => {
    const c = { added: 0, modified: 0, deleted: 0, renamed: 0 };
    for (const f of changes.files) c[f.status]++;
    return c;
  });
</script>

<div class="panel" data-testid="diff-panel">
  {#if !change}
    <h2>Cambios {a.slice(0, 7)} → {b.slice(0, 7)}</h2>
    <p class="stats">
      {changes.files.length} archivos: {counts.added} añadidos · {counts.modified} modificados · {counts.deleted} eliminados{counts.renamed
        ? ` · ${counts.renamed} renombrados`
        : ''}
    </p>
    {#await global}
      <div class="empty">Cargando…</div>
    {:then text}
      {#if text === null}
        <div class="empty">Este diff no tiene explicación global (explain.md) todavía.</div>
      {:else}
        <Markdown source={text ?? ''} doc={doc('explain.md')} />
      {/if}
    {:catch err}
      <div class="empty">Error: {err.message}</div>
    {/await}
  {:else}
    <h2>
      {change.path}
      {#if badge && !change.eolOnly}<span class="status">{badge.title}</span>{/if}
    </h2>
    {#if change.eolOnly}
      <p class="eol" data-testid="eol-only">solo finales de línea</p>
    {/if}
    {#await fileExplain}
      <div class="empty">Cargando…</div>
    {:then e}
      {@const d = doc(`explain/${change.path}.json`)}
      {#if e}
        <div class="summary"><Markdown source={e.summary} doc={d} /></div>
      {:else if !change.eolOnly}
        <div class="empty">Este archivo no tiene explicación del cambio todavía.</div>
      {/if}
      {#each change.hunks as h, i (i)}
        {@const bodies = e?.hunks.filter((x) => x.index === i) ?? []}
        <!-- svelte-ignore a11y_click_events_have_key_events, a11y_no_static_element_interactions -->
        <section
          class="card"
          class:active={activeHunk === i}
          onclick={(ev) => {
            if ((ev.target as Element).closest('a, button, iframe, .rc-mermaid')) return;
            onHunk(i);
          }}
        >
          <header><code>{hunkLabel(h, i)}</code></header>
          {#each bodies as body, n (n)}
            <Markdown source={body.body} doc={d} />
          {:else}
            <p class="none">Sin explicación para este hunk.</p>
          {/each}
        </section>
      {/each}
      {#each e?.hunks.filter((x) => x.index >= change.hunks.length) ?? [] as orphan, n (n)}
        <section class="card orphan">
          <header><code>hunk {orphan.index + 1} (no existe en changes.json)</code></header>
          <Markdown source={orphan.body} doc={d} />
        </section>
      {/each}
    {:catch err}
      <div class="empty">Error: {err.message}</div>
    {/await}
  {/if}
</div>

<style>
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
  .status {
    font-family: var(--font-ui);
    font-size: 12px;
    font-weight: normal;
    color: var(--fg-muted);
    margin-left: 6px;
  }
  .eol {
    color: var(--fg-muted);
    font-size: 13px;
    font-style: italic;
  }
  .stats {
    color: var(--fg-muted);
    font-size: 13px;
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
  }
  .card:hover {
    border-left-color: var(--fg-faint);
  }
  .card.active {
    border-left-color: var(--accent);
    background: var(--bg-block);
  }
  .card.orphan {
    cursor: default;
    border-left-color: var(--danger);
  }
  .card header code {
    font-size: 12px;
    color: var(--fg-muted);
  }
  .none {
    color: var(--fg-muted);
    font-size: 13px;
  }
</style>
