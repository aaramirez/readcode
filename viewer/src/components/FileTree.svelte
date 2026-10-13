<script lang="ts">
  import { tick } from 'svelte';
  import { SvelteSet } from 'svelte/reactivity';
  import { ancestors, buildTree, filterTree, type TreeNode } from '../lib/tree';
  import type { DiffBadge } from '../lib/diff';
  import type { Tree } from '../lib/types';

  interface Props {
    tree: Tree;
    /** Currently selected entry (from the route), revealed and highlighted. */
    selected: { kind: 'file' | 'dir'; path: string } | null;
    onFile: (path: string) => void;
    onDir: (path: string) => void;
    /** Diff mode: A/M/D/R badge per changed file (replaces the language badge). */
    badges?: Map<string, DiffBadge>;
    /** Issue count per file/dir path (warning icon). */
    warnings?: Map<string, number>;
    /** Diff mode: no root row, no excluded toggle. */
    diffMode?: boolean;
  }

  let { tree, selected, onFile, onDir, badges, warnings, diffMode = false }: Props = $props();

  function warnTitle(path: string): string {
    const n = warnings?.get(path) ?? 0;
    return n === 1 ? '1 problema reportado' : `${n} problemas reportados`;
  }

  let query = $state('');
  let showExcluded = $state(false);
  const expanded = new SvelteSet<string>();
  let container: HTMLElement | undefined = $state();

  const root = $derived(buildTree(tree, showExcluded));
  const filtered = $derived(filterTree(root, query));
  const visibleRoot = $derived(filtered ? filtered.root : root);

  // In diff mode the (few) changed files start visible: `expanded` then holds collapsed dirs.
  function isOpen(node: TreeNode): boolean {
    const own = diffMode ? !expanded.has(node.path) : expanded.has(node.path);
    return filtered ? filtered.expand.has(node.path) || own : own;
  }

  function toggle(node: TreeNode) {
    if (expanded.has(node.path)) expanded.delete(node.path);
    else expanded.add(node.path);
  }

  function isSelected(node: TreeNode): boolean {
    return selected !== null && selected.kind === node.kind && selected.path === node.path;
  }

  // Reveal the selected entry: expand its ancestors and scroll it into view.
  $effect(() => {
    const sel = selected;
    if (!sel || sel.path === '') return;
    for (const a of ancestors(sel.path)) {
      if (diffMode) expanded.delete(a);
      else expanded.add(a);
    }
    tick().then(() => {
      const el = container?.querySelector<HTMLElement>(`[data-path="${CSS.escape(sel.path)}"]`);
      el?.scrollIntoView({ block: 'nearest' });
    });
  });
</script>

<div class="tree">
  <div class="tools">
    <input type="search" placeholder="Filtrar archivos…" bind:value={query} aria-label="Filtrar archivos" />
    {#if !diffMode}
      <label class="toggle">
        <input type="checkbox" bind:checked={showExcluded} /> mostrar excluidos
      </label>
    {/if}
  </div>
  <div class="items" bind:this={container} role="tree">
    {#if !diffMode}
    <button
      class="row dir"
      class:selected={selected?.kind === 'dir' && selected.path === ''}
      style="padding-left: 6px"
      onclick={() => onDir('')}
    >
      <span class="caret"></span><span class="name">/ (raíz)</span>
    </button>
    {/if}
    {#if visibleRoot.children.length === 0}
      <div class="empty">Sin coincidencias.</div>
    {/if}
    {@render children(visibleRoot.children, 1)}
  </div>
</div>

{#snippet children(nodes: TreeNode[], depth: number)}
  {#each nodes as node (node.path + ':' + node.kind)}
    {#if node.kind === 'dir'}
      {@const open = isOpen(node)}
      <button
        class="row dir"
        class:selected={isSelected(node)}
        class:excluded={node.excluded}
        data-path={node.path}
        style="padding-left: {6 + depth * 12}px"
        role="treeitem"
        aria-expanded={open}
        aria-selected={isSelected(node)}
        onclick={() => {
          if (!open) toggle(node);
          else if (isSelected(node)) toggle(node);
          if (!node.excluded) onDir(node.path);
        }}
      >
        <span
          class="caret"
          role="presentation"
          onclick={(e) => {
            e.stopPropagation();
            toggle(node);
          }}>{open ? '▾' : '▸'}</span
        ><span class="name">{node.name}</span>
        {#if warnings?.has(node.path)}<span class="warn" title={warnTitle(node.path)}>⚠</span>{/if}
      </button>
      {#if open}
        {@render children(node.children, depth + 1)}
      {/if}
    {:else}
      <button
        class="row file"
        class:selected={isSelected(node)}
        class:excluded={node.excluded}
        data-path={node.path}
        style="padding-left: {6 + depth * 12}px"
        role="treeitem"
        aria-selected={isSelected(node)}
        title={node.excluded ? 'Excluido del estudio' : node.path}
        onclick={() => onFile(node.path)}
      >
        <span class="caret"></span><span class="name" class:deleted={badges?.get(node.path)?.status === 'deleted'}>{node.name}</span>
        {#if warnings?.has(node.path)}<span class="warn" title={warnTitle(node.path)}>⚠</span>{/if}
        {#if badges?.has(node.path)}
          {@const diff = badges.get(node.path)!}
          <span class="badge diff diff-{diff.badge}" title={diff.title}>{diff.badge}</span>
        {:else if node.language}<span class="badge">{node.language}</span>{/if}
      </button>
    {/if}
  {/each}
{/snippet}

<style>
  .tree {
    display: flex;
    flex-direction: column;
    height: 100%;
    min-height: 0;
  }
  .tools {
    display: flex;
    flex-direction: column;
    gap: 4px;
    padding: 6px;
    border-bottom: 1px solid var(--border);
  }
  .tools input[type='search'] {
    width: 100%;
  }
  .toggle {
    font-size: 12px;
    color: var(--fg-muted);
    display: flex;
    align-items: center;
    gap: 4px;
  }
  .items {
    overflow: auto;
    flex: 1;
    padding: 4px 0;
  }
  .row {
    display: flex;
    align-items: center;
    width: 100%;
    border: none;
    border-radius: 0;
    background: transparent;
    padding: 2px 6px;
    text-align: left;
    white-space: nowrap;
    gap: 4px;
  }
  .row:hover {
    background: var(--bg-hover);
  }
  .row.selected {
    background: var(--bg-selected);
  }
  .row.excluded {
    color: var(--fg-faint);
    font-style: italic;
  }
  .caret {
    width: 12px;
    flex: none;
    color: var(--fg-muted);
    font-size: 11px;
  }
  .name {
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .warn {
    color: var(--warn);
    font-size: 12px;
    flex: none;
  }
  .name.deleted {
    text-decoration: line-through;
    color: var(--fg-muted);
  }
  .badge.diff {
    font-family: var(--font-code);
    font-weight: 700;
    color: var(--accent-fg);
  }
  .badge.diff-A {
    background: var(--added);
  }
  .badge.diff-M {
    background: var(--warn);
  }
  .badge.diff-D {
    background: var(--danger);
  }
  .badge.diff-R {
    background: var(--accent);
  }
  .badge {
    margin-left: auto;
    font-size: 10px;
    padding: 0 5px;
    border-radius: 8px;
    background: var(--badge-bg);
    color: var(--fg-muted);
  }
</style>
