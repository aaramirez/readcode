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
  }

  let { catalog, studyName, study, sha, theme, onStudy, onSha, onTheme }: Props = $props();

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
  <button disabled title="Disponible próximamente">Comparar…</button>
  <div class="nav">
    <button title="Atrás" aria-label="Atrás" onclick={() => history.back()}>←</button>
    <button title="Adelante" aria-label="Adelante" onclick={() => history.forward()}>→</button>
  </div>
  <input class="search" type="search" placeholder="Buscar (Ctrl+K) — próximamente" disabled aria-label="Buscar" />
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
  }
</style>
