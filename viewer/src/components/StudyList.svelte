<script lang="ts">
  import { format } from '../lib/router';
  import type { Catalog } from '../lib/types';

  let { catalog }: { catalog: Catalog | null } = $props();
</script>

<div class="studies">
  <h1>Estudios</h1>
  {#if !catalog}
    <p class="empty">No se encontró <code>catalog.json</code>. Ejecuta <code>readcode catalog</code> en el kb.</p>
  {:else if catalog.studies.length === 0}
    <p class="empty">El kb no tiene estudios todavía.</p>
  {:else}
    <ul>
      {#each catalog.studies as s (s.name)}
        <li>
          <a href={format({ kind: 'study', study: s.name })}>{s.title}</a>
          <span class="meta">{s.name} · {s.snapshots} commit{s.snapshots === 1 ? '' : 's'} · actualizado {s.updated.slice(0, 10)}</span>
          <span class="repo">{s.repo.url}</span>
        </li>
      {/each}
    </ul>
  {/if}
</div>

<style>
  .studies {
    max-width: 50rem;
    margin: 2rem auto;
    padding: 0 1rem;
  }
  ul {
    list-style: none;
    padding: 0;
  }
  li {
    display: flex;
    flex-direction: column;
    gap: 2px;
    padding: 10px 12px;
    border: 1px solid var(--border);
    border-radius: 6px;
    margin-bottom: 8px;
  }
  li a {
    font-weight: 600;
    font-size: 16px;
  }
  .meta,
  .repo {
    color: var(--fg-muted);
    font-size: 12px;
  }
  .repo {
    font-family: var(--font-code);
    overflow-wrap: anywhere;
  }
</style>
