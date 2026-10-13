<script lang="ts">
  // Ctrl+K palette over tree paths, symbol definitions and explanation block
  // titles. Files and symbols are indexed at once; block titles come from the
  // snapshot's search.json (one request, written by `readcode validate`) or, for
  // kbs without it, from every explain/<path>.json fetched in the background
  // (6 at a time), joining the results as they arrive. Enter (or click) navigates.
  import { onMount, tick } from 'svelte';
  import type { StudyData } from '../lib/data';
  import { format, navigate } from '../lib/router';
  import { SearchIndex, fileItems, loadBlockItems, rankItems, symbolItems, type SearchItem } from '../lib/search';
  import type { Tree } from '../lib/types';

  interface Props {
    data: StudyData;
    study: string;
    sha: string;
    tree: Tree;
    onClose: () => void;
  }

  let { data, study, sha, tree, onClose }: Props = $props();

  let query = $state('');
  // The index grows in place (no copies); `version` is the reactive signal of a change.
  const index = new SearchIndex();
  let version = $state(0);
  let loadingBlocks = $state(true);
  let pending = $state(0);
  let cursor = $state(0);

  function add(items: readonly SearchItem[]) {
    index.add(items);
    version = index.version;
  }

  // The palette is mounted per opening, so the index is built for the props at mount time.
  onMount(() => {
    let cancelled = false;
    let frame = 0;
    add(fileItems(tree, study, sha));
    data.symbols(sha).then(
      (s) => {
        if (!cancelled && s) add(symbolItems(s, study, sha));
      },
      () => {},
    );

    let batch: SearchItem[] = [];
    const flush = () => {
      frame = 0;
      if (cancelled || batch.length === 0) return;
      add(batch);
      batch = [];
    };
    loadBlockItems(
      data,
      tree,
      study,
      sha,
      (items) => {
        for (const item of items) batch.push(item); // no spread: search.json can be large
        if (!frame) frame = requestAnimationFrame(flush);
      },
      {
        cancelled: () => cancelled,
        onPending: (n) => {
          loadingBlocks = false;
          pending = n;
        },
      },
    ).finally(() => {
      if (!cancelled) loadingBlocks = false;
    });
    return () => {
      cancelled = true;
      cancelAnimationFrame(frame);
    };
  });

  const results = $derived.by(() => {
    void version;
    return rankItems(index.items, query, 50);
  });
  const count = $derived.by(() => {
    void version;
    return index.items.length;
  });
  $effect(() => {
    void query;
    cursor = 0;
  });

  let input: HTMLInputElement | undefined = $state();
  let list: HTMLElement | undefined = $state();
  onMount(() => input?.focus());

  function go(item: SearchItem | undefined) {
    if (!item) return;
    onClose();
    navigate(item.route);
  }

  function onkeydown(e: KeyboardEvent) {
    if (e.key === 'Escape') {
      e.preventDefault();
      onClose();
    } else if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault();
      if (results.length === 0) return;
      cursor = (cursor + (e.key === 'ArrowDown' ? 1 : -1) + results.length) % results.length;
      tick().then(() => list?.querySelector('.cursor')?.scrollIntoView({ block: 'nearest' }));
    } else if (e.key === 'Enter') {
      e.preventDefault();
      go(results[cursor]);
    }
  }

  const KIND: Record<SearchItem['kind'], string> = { file: 'archivo', symbol: 'símbolo', block: 'bloque' };
</script>

<!-- svelte-ignore a11y_click_events_have_key_events, a11y_no_static_element_interactions -->
<div class="backdrop" onclick={onClose}>
  <!-- svelte-ignore a11y_click_events_have_key_events, a11y_no_static_element_interactions -->
  <div class="palette" role="dialog" tabindex="-1" aria-label="Buscar" onclick={(e) => e.stopPropagation()}>
    <input
      bind:this={input}
      bind:value={query}
      {onkeydown}
      type="search"
      placeholder="Buscar archivos, símbolos y bloques…"
      aria-label="Buscar"
      role="combobox"
      aria-expanded={results.length > 0}
      aria-controls="search-results"
    />
    <ul id="search-results" bind:this={list} role="listbox">
      {#each results as r, i (i)}
        <li role="option" aria-selected={i === cursor} class:cursor={i === cursor}>
          <a
            href={format(r.route)}
            onclick={(e) => {
              e.preventDefault();
              go(r);
            }}
            onmousemove={() => (cursor = i)}
          >
            <span class="kind kind-{r.kind}">{KIND[r.kind]}</span>
            <span class="text">{r.text}</span>
            {#if r.detail}<span class="detail">{r.detail}</span>{/if}
          </a>
        </li>
      {/each}
    </ul>
    <div class="foot">
      {#if query.trim() && results.length === 0}Sin resultados. ·{/if}
      {loadingBlocks ? 'indexando explicaciones…' : pending > 0 ? `indexando explicaciones… (${pending})` : `${count} entradas`}
      · ↑↓ elegir · Enter abrir · Esc cerrar
    </div>
  </div>
</div>

<style>
  .backdrop {
    position: fixed;
    inset: 0;
    background: rgb(0 0 0 / 0.3);
    z-index: 100;
    display: flex;
    justify-content: center;
    align-items: flex-start;
    padding-top: 10vh;
  }
  .palette {
    width: min(40rem, 92vw);
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: 8px;
    box-shadow: 0 10px 30px rgb(0 0 0 / 0.25);
    display: flex;
    flex-direction: column;
    max-height: 70vh;
  }
  input {
    margin: 10px;
    padding: 6px 10px;
    font-size: 15px;
  }
  ul {
    list-style: none;
    margin: 0;
    padding: 0 0 4px;
    overflow: auto;
  }
  li a {
    display: flex;
    gap: 8px;
    align-items: baseline;
    padding: 5px 12px;
    color: var(--fg);
    text-decoration: none;
  }
  li.cursor a {
    background: var(--bg-selected);
  }
  .kind {
    flex: none;
    width: 4.5rem;
    font-size: 11px;
    color: var(--fg-muted);
  }
  .text {
    font-family: var(--font-code);
    font-size: 13px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .kind-block + .text {
    font-family: var(--font-ui);
  }
  .detail {
    margin-left: auto;
    color: var(--fg-muted);
    font-size: 12px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    max-width: 50%;
  }
  .foot {
    border-top: 1px solid var(--border);
    padding: 5px 12px;
    font-size: 12px;
    color: var(--fg-muted);
  }
</style>
