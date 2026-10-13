<script lang="ts">
  // Right pane while a tour plays: step title + narration (shared renderer,
  // doc key "tours/<id>.json"), ◀ ▶ controls ([ and ] in App), progress, exit.
  import type { StudyData } from '../lib/data';
  import { format } from '../lib/router';
  import { stepNav } from '../lib/tours';
  import type { Tour } from '../lib/types';
  import Markdown from './Markdown.svelte';

  interface Props {
    data: StudyData;
    study: string;
    sha: string;
    tour: Tour;
    /** Current step, 1-based and already clamped. */
    step: number;
  }

  let { data, study, sha, tour, step }: Props = $props();

  const total = $derived(tour.steps.length);
  const nav = $derived(stepNav(total, step));
  const current = $derived(tour.steps[step - 1]);
  const doc = $derived({ data, study, sha, docKey: `tours/${tour.id}.json` });

  function stepHref(n: number): string {
    return format({ kind: 'tour', study, sha, id: tour.id, step: n });
  }
  const exitHref = $derived(
    current
      ? format({ kind: 'file', study, sha, path: current.path, range: { start: current.range[0], end: current.range[1] } })
      : format({ kind: 'overview', study, sha }),
  );
</script>

<div class="tour" data-testid="tour-panel">
  <div class="head">
    <span class="tour-title">{tour.title}</span>
    <a class="exit" href={exitHref} title="Salir del tour y seguir en este archivo">salir del tour ✕</a>
  </div>
  <div class="controls">
    {#if nav.prev}
      <a class="btn" href={stepHref(nav.prev)} title="Paso anterior ( [ )">◀</a>
    {:else}
      <span class="btn disabled" aria-disabled="true">◀</span>
    {/if}
    <span class="progress">paso {step} de {total}</span>
    {#if nav.next}
      <a class="btn" href={stepHref(nav.next)} title="Paso siguiente ( ] )">▶</a>
    {:else}
      <span class="btn disabled" aria-disabled="true">▶</span>
    {/if}
    <progress max={total} value={step}></progress>
  </div>
  {#if current}
    <h2>{current.title}</h2>
    <div class="where"><code>{current.path}</code> · L{current.range[0]}–{current.range[1]}</div>
    {#key `${tour.id}:${step}`}
      <Markdown source={current.body} {doc} />
    {/key}
  {/if}
  <p class="keys">Teclas: <kbd>[</kbd> anterior · <kbd>]</kbd> siguiente</p>
</div>

<style>
  .tour {
    padding: 8px 12px 40px;
    overflow: auto;
    height: 100%;
  }
  .head {
    display: flex;
    align-items: baseline;
    gap: 8px;
  }
  .tour-title {
    font-weight: 600;
    flex: 1;
  }
  .exit {
    font-size: 12px;
    white-space: nowrap;
  }
  .controls {
    display: flex;
    align-items: center;
    gap: 8px;
    margin: 10px 0;
    flex-wrap: wrap;
  }
  .btn {
    border: 1px solid var(--border);
    border-radius: 4px;
    padding: 2px 10px;
    text-decoration: none;
    background: var(--bg-alt);
    color: var(--fg);
  }
  .btn.disabled {
    opacity: 0.4;
  }
  .progress {
    font-size: 13px;
  }
  progress {
    flex: 1;
    min-width: 60px;
    height: 6px;
  }
  h2 {
    font-size: 16px;
    margin: 8px 0 2px;
  }
  .where {
    color: var(--fg-muted);
    font-size: 12px;
    margin-bottom: 8px;
  }
  .keys {
    margin-top: 20px;
    color: var(--fg-muted);
    font-size: 12px;
  }
  kbd {
    font-family: var(--font-code);
    border: 1px solid var(--border);
    border-radius: 3px;
    padding: 0 4px;
  }
</style>
