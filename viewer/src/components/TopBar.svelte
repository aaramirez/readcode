<script lang="ts">
  import type { Theme } from '../lib/prefs';
  import type { Catalog, Study } from '../lib/types';

  interface Props {
    catalog: Catalog | null;
    studyName: string | null;
    study: Study | null;
    sha: string | null;
    theme: Theme;
    onStudy: (name: string) => void;
    onSha: (sha: string) => void;
    onTheme: () => void;
    onBack: () => void;
    onForward: () => void;
    /** Open the "Comparar…" dialog (null: not available). */
    onCompare: (() => void) | null;
    /** Open the Ctrl+K palette (null: not available). */
    onSearch: (() => void) | null;
    /** Diff view: the commit selector shows B. */
    diffLabel?: string | null;
  }

  let {
    catalog,
    studyName,
    study,
    sha,
    theme,
    onStudy,
    onSha,
    onTheme,
    onBack,
    onForward,
    onCompare,
    onSearch,
    diffLabel = null,
  }: Props = $props();

  const snapshots = $derived(
    study ? [...study.snapshots].sort((a, b) => Date.parse(b.date) - Date.parse(a.date)) : [],
  );

  const THEME_LABEL: Record<Theme, string> = { auto: 'Tema: auto', light: 'Tema: claro', dark: 'Tema: oscuro' };
</script>

<header class="topbar">
  <a class="brand" href="#/">readcode</a>
  <select
    aria-label="Estudio"
    value={studyName ?? ''}
    onchange={(e) => onStudy((e.currentTarget as HTMLSelectElement).value)}
  >
    {#if !studyName}<option value="" disabled>Estudio…</option>{/if}
    {#each catalog?.studies ?? [] as s (s.name)}
      <option value={s.name}>{s.title}</option>
    {/each}
  </select>
  <select
    aria-label="Commit"
    class="commit"
    disabled={snapshots.length === 0}
    value={sha ?? ''}
    onchange={(e) => onSha((e.currentTarget as HTMLSelectElement).value)}
  >
    {#if !sha}<option value="" disabled>Commit…</option>{/if}
    {#each snapshots as s (s.sha)}
      <option value={s.sha}>{s.sha.slice(0, 7)} · {s.date.slice(0, 10)} · {s.message.split('\n')[0]}</option>
    {/each}
  </select>
  <button
    disabled={!onCompare || (study?.snapshots.length ?? 0) < 2}
    title={diffLabel ?? 'Comparar dos commits'}
    class:active={!!diffLabel}
    onclick={() => onCompare?.()}>{diffLabel ?? 'Comparar…'}</button
  >
  <div class="nav">
    <button title="Atrás" aria-label="Atrás" onclick={onBack}>←</button>
    <button title="Adelante" aria-label="Adelante" onclick={onForward}>→</button>
  </div>
  <button class="search" disabled={!onSearch} onclick={() => onSearch?.()} aria-label="Buscar (Ctrl+K)">
    <span>Buscar…</span><kbd>Ctrl+K</kbd>
  </button>
  <button class="theme" onclick={onTheme}>{THEME_LABEL[theme]}</button>
</header>

<style>
  .topbar {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 6px 10px;
    border-bottom: 1px solid var(--border);
    background: var(--bg-alt);
    flex: none;
  }
  .brand {
    font-weight: 700;
    text-decoration: none;
    color: var(--fg);
    margin-right: 4px;
  }
  .commit {
    max-width: 28rem;
    font-family: var(--font-code);
    font-size: 12px;
  }
  .nav {
    display: flex;
    gap: 2px;
  }
  .search {
    flex: 1;
    min-width: 8rem;
    max-width: 24rem;
    margin-left: auto;
    display: flex;
    justify-content: space-between;
    align-items: center;
    background: var(--bg);
    color: var(--fg-muted);
    text-align: left;
  }
  .search kbd {
    font-family: var(--font-code);
    font-size: 11px;
    border: 1px solid var(--border);
    border-radius: 3px;
    padding: 0 4px;
  }
  button.active {
    background: var(--bg-selected);
    font-family: var(--font-code);
    font-size: 12px;
  }
</style>
