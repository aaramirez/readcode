<script lang="ts">
  // Tours tab (no tour playing): the snapshot's tours with title, description and step count.
  import type { StudyData } from '../lib/data';
  import { format } from '../lib/router';
  import type { Tour } from '../lib/types';
  import Markdown from './Markdown.svelte';

  interface Props {
    data: StudyData;
    study: string;
    sha: string;
    /** A tour link was clicked (its hash may equal the current one: no hashchange). */
    onStart?: (id: string) => void;
  }

  let { data, study, sha, onStart }: Props = $props();

  const list = $derived(
    data.tours(sha).then((entries) =>
      Promise.all(entries.map((e) => data.tour(sha, e.id).then((tour): { id: string; tour: Tour | null } => ({ id: e.id, tour })))),
    ),
  );
</script>

<div class="tours" data-testid="tours">
  {#await list}
    <div class="empty">Cargando…</div>
  {:then tours}
    {#if tours.length === 0}
      <div class="empty">Este commit no tiene tours.</div>
    {:else}
      {#each tours as t (t.id)}
        <section class="card">
          {#if t.tour}
            <header>
              <a class="title" href={format({ kind: 'tour', study, sha, id: t.id, step: 1 })} onclick={() => onStart?.(t.id)}>{t.tour.title}</a>
              <span class="chip">{t.tour.steps.length} {t.tour.steps.length === 1 ? 'paso' : 'pasos'}</span>
            </header>
            <Markdown source={t.tour.description} doc={{ data, study, sha, docKey: `tours/${t.id}.json` }} />
            <a class="start" data-testid="tour-start" href={format({ kind: 'tour', study, sha, id: t.id, step: 1 })} onclick={() => onStart?.(t.id)}>Empezar ▶</a>
          {:else}
            <header><span class="title">{t.id}</span></header>
            <div class="empty">No se encontró tours/{t.id}.json.</div>
          {/if}
        </section>
      {/each}
    {/if}
  {:catch err}
    <div class="empty">Error al cargar los tours: {err.message}</div>
  {/await}
</div>

<style>
  .tours {
    padding: 8px 24px 24px;
    overflow: auto;
    height: 100%;
  }
  .card {
    max-width: 50rem;
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 10px 14px;
    margin: 10px 0;
  }
  header {
    display: flex;
    align-items: baseline;
    gap: 10px;
  }
  .title {
    font-weight: 600;
    font-size: 15px;
    flex: 1;
  }
  .chip {
    font-size: 11px;
    background: var(--badge-bg);
    color: var(--fg-muted);
    border-radius: 10px;
    padding: 1px 8px;
    white-space: nowrap;
  }
  .start {
    display: inline-block;
    margin-top: 4px;
  }
</style>
