<script lang="ts">
  // Center view of a d/ route: the directory's contents (its summary is in the
  // right panel).
  import type { StudyData } from '../lib/data';
  import { format } from '../lib/router';
  import type { Tree } from '../lib/types';

  let { data, study, sha, tree, path }: { data: StudyData; study: string; sha: string; tree: Tree; path: string } =
    $props();

  const dir = $derived(data.dir(sha, path));

  // Fallback listing from tree.json when the dir has no summary file.
  const treeChildren = $derived.by(() => {
    const prefix = path === '' ? '' : path + '/';
    const seen = new Map<string, 'file' | 'dir'>();
    for (const f of tree.files) {
      if (!f.path.startsWith(prefix)) continue;
      const rest = f.path.slice(prefix.length);
      const slash = rest.indexOf('/');
      const child = prefix + (slash < 0 ? rest : rest.slice(0, slash));
      if (!seen.has(child)) seen.set(child, slash < 0 ? 'file' : 'dir');
    }
    return [...seen.entries()]
      .map(([p, kind]) => ({ path: p, kind, oneLine: '' }))
      .sort((a, b) => (a.kind === b.kind ? a.path.localeCompare(b.path) : a.kind === 'dir' ? -1 : 1));
  });

  function name(p: string): string {
    return p.slice(p.lastIndexOf('/') + 1);
  }
</script>

<div class="dir">
  <h2>{path === '' ? 'Raíz del repositorio' : path + '/'}</h2>
  {#await dir}
    <div class="empty">Cargando…</div>
  {:then d}
    {@const children = d?.children.length ? d.children : treeChildren}
    {#if children.length === 0}
      <div class="empty">Directorio vacío o inexistente en este commit.</div>
    {:else}
      <table>
        <tbody>
          {#each children as c (c.path)}
            <tr>
              <td class="name">
                <a href={format(c.kind === 'dir' ? { kind: 'dir', study, sha, path: c.path } : { kind: 'file', study, sha, path: c.path })}
                  >{name(c.path)}{c.kind === 'dir' ? '/' : ''}</a
                >
              </td>
              <td class="one-line">{c.oneLine}</td>
            </tr>
          {/each}
        </tbody>
      </table>
      <p class="hint">Elige un archivo para ver su código. El resumen del directorio está en el panel derecho.</p>
    {/if}
  {:catch err}
    <div class="empty">Error: {err.message}</div>
  {/await}
</div>

<style>
  .dir {
    padding: 8px 24px 24px;
    overflow: auto;
    height: 100%;
  }
  h2 {
    font-family: var(--font-code);
    font-size: 16px;
  }
  table {
    border-collapse: collapse;
    width: 100%;
    max-width: 60rem;
  }
  td {
    padding: 5px 10px 5px 0;
    border-bottom: 1px solid var(--border);
    vertical-align: baseline;
  }
  .name {
    font-family: var(--font-code);
    white-space: nowrap;
  }
  .one-line {
    color: var(--fg-muted);
  }
  .hint {
    color: var(--fg-muted);
    font-size: 12px;
  }
</style>
