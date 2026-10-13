<script lang="ts">
  // "Comparar…": pick A and B among the studied snapshots. Only pairs with a
  // generated diffs/<a>..<b>/changes.json can be opened.
  import { onMount, untrack } from 'svelte';
  import type { StudyData } from '../lib/data';
  import type { Study } from '../lib/types';

  interface Props {
    data: StudyData;
    study: Study;
    /** Current snapshot (default B). */
    sha: string;
    onCompare: (a: string, b: string) => void;
    onClose: () => void;
  }

  let { data, study, sha, onCompare, onClose }: Props = $props();

  // oldest first, so the natural pick is A = older, B = newer
  const snapshots = $derived([...study.snapshots].sort((x, y) => Date.parse(x.date) - Date.parse(y.date)));

  // initial picks only: later prop changes must not reset the user's choice
  function initialA(): string {
    const list = [...study.snapshots].sort((x, y) => Date.parse(x.date) - Date.parse(y.date));
    const i = list.findIndex((s) => s.sha === sha);
    return (i > 0 ? list[i - 1] : list[0])?.sha ?? '';
  }
  let a = $state(untrack(initialA));
  let b = $state(untrack(() => sha));

  // which B's have a generated diff for the chosen A
  let available = $state<{ a: string; has: Set<string> } | null>(null);
  $effect(() => {
    const from = a;
    const others = study.snapshots.filter((s) => s.sha !== from);
    Promise.all(others.map((s) => data.changes(from, s.sha).then((c) => (c ? s.sha : null), () => null))).then((found) => {
      if (a === from) available = { a: from, has: new Set(found.filter((x): x is string => x !== null)) };
    });
  });
  const has = $derived(available?.a === a ? available.has : null);
  const ok = $derived(a !== b && !!has?.has(b));

  function label(s: { sha: string; date: string; message: string }): string {
    return `${s.sha.slice(0, 7)} · ${s.date.slice(0, 10)} · ${s.message.split('\n')[0]}`;
  }

  let dialog: HTMLDialogElement | undefined = $state();
  onMount(() => dialog?.showModal());

  function submit(e: SubmitEvent) {
    e.preventDefault();
    if (ok) onCompare(a, b);
  }
</script>

<dialog bind:this={dialog} onclose={onClose} aria-labelledby="compare-title">
  <form onsubmit={submit}>
    <h2 id="compare-title">Comparar commits</h2>
    <label>
      A (antes)
      <select bind:value={a}>
        {#each snapshots as s (s.sha)}<option value={s.sha}>{label(s)}</option>{/each}
      </select>
    </label>
    <label>
      B (después)
      <select bind:value={b}>
        {#each snapshots as s (s.sha)}
          <option value={s.sha} disabled={s.sha === a || (has !== null && !has.has(s.sha))}>
            {label(s)}{s.sha !== a && has !== null && !has.has(s.sha) ? ' — sin diff generado' : ''}
          </option>
        {/each}
      </select>
    </label>
    <p class="status" role="status">
      {#if a === b}
        Elige dos commits distintos.
      {:else if has === null}
        Buscando diffs generados…
      {:else if !ok}
        sin diff generado — ejecuta <code>/readcode diff {study.name} {a.slice(0, 7)} {b.slice(0, 7)}</code>
      {:else}
        Diff disponible.
      {/if}
    </p>
    <div class="actions">
      <button type="button" onclick={() => dialog?.close()}>Cancelar</button>
      <button type="submit" class="primary" disabled={!ok}>Comparar</button>
    </div>
  </form>
</dialog>

<style>
  dialog {
    border: 1px solid var(--border);
    border-radius: 8px;
    background: var(--bg);
    color: var(--fg);
    padding: 16px 20px;
    min-width: min(32rem, 90vw);
  }
  dialog::backdrop {
    background: rgb(0 0 0 / 0.35);
  }
  h2 {
    font-size: 16px;
    margin: 0 0 12px;
  }
  label {
    display: flex;
    flex-direction: column;
    gap: 3px;
    margin-bottom: 10px;
    font-size: 13px;
    color: var(--fg-muted);
  }
  select {
    font-family: var(--font-code);
    font-size: 12px;
    color: var(--fg);
  }
  .status {
    min-height: 1.4em;
    font-size: 13px;
  }
  .actions {
    display: flex;
    justify-content: flex-end;
    gap: 8px;
  }
  .primary:not(:disabled) {
    background: var(--accent);
    color: var(--accent-fg);
    border-color: var(--accent);
  }
</style>
