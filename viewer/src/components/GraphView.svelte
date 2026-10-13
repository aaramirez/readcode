<script lang="ts">
  // Graph tab: graphify's graph/graph.json in Cytoscape (cose layout), filtered by
  // community and text. Clicking a node opens its file at its line; the route
  // graph/<path> centers and highlights that file's nodes.
  import type { Core, ElementDefinition } from 'cytoscape';
  import { untrack } from 'svelte';
  import type { StudyData } from '../lib/data';
  import { MAX_NODES, parseGraph, selectElements, type GraphModel } from '../lib/graph';
  import { navigate } from '../lib/router';
  import { themeState } from '../lib/theme.svelte';
  import type { Tree } from '../lib/types';

  interface Props {
    data: StudyData;
    study: string;
    sha: string;
    tree: Tree;
    /** File whose nodes are centered and highlighted. */
    focus?: string;
  }

  let { data, study, sha, tree, focus }: Props = $props();

  // ---- load + parse
  let model = $state<{ key: string; graph: GraphModel | null; error?: string } | null>(null);
  const key = $derived(`${study}@${sha}`);
  $effect(() => {
    const k = key;
    const paths = new Set(tree.files.map((f) => f.path));
    data.graph(sha).then(
      (raw) => {
        if (key !== k) return;
        const graph = raw ? parseGraph(raw, paths) : null;
        model = { key: k, graph };
        selected = new Set(graph?.communities.map((c) => c.id) ?? []);
      },
      (e: Error) => {
        if (key === k) model = { key: k, graph: null, error: e.message };
      },
    );
  });
  const graph = $derived(model?.key === key ? model.graph : null);

  // ---- filters
  let selected = $state<Set<string>>(new Set());
  let text = $state('');
  let debounced = $state('');
  $effect(() => {
    const t = text;
    const timer = setTimeout(() => (debounced = t), 200);
    return () => clearTimeout(timer);
  });

  function toggle(id: string) {
    const next = new Set(selected);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    selected = next;
  }
  function setAll(on: boolean) {
    selected = new Set(on && graph ? graph.communities.map((c) => c.id) : []);
  }

  const selection = $derived(graph ? selectElements(graph, { communities: selected, text: debounced, focus }) : null);
  const colors = $derived(new Map(graph?.communities.map((c) => [c.id, c.color]) ?? []));
  const focusCount = $derived(focus && graph ? graph.nodes.filter((n) => n.path === focus).length : 0);

  // ---- cytoscape
  let host: HTMLElement | undefined = $state();
  let cy = $state<Core | null>(null);

  function cssVar(name: string): string {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  }

  function style() {
    const fg = cssVar('--fg') || '#333';
    const bg = cssVar('--bg') || '#fff';
    const edge = cssVar('--fg-faint') || '#aaa';
    const accent = cssVar('--accent') || '#2f6fdf';
    return [
      {
        selector: 'node',
        style: {
          'background-color': 'data(color)',
          label: 'data(label)',
          color: fg,
          'font-size': 10,
          'text-valign': 'bottom',
          'text-margin-y': 3,
          'text-outline-color': bg,
          'text-outline-width': 2,
          width: 14,
          height: 14,
        },
      },
      { selector: 'node[?path]', style: { shape: 'ellipse' } },
      { selector: 'node[!path]', style: { shape: 'round-rectangle', opacity: 0.6 } },
      {
        selector: 'edge',
        style: { width: 1, 'line-color': edge, 'curve-style': 'haystack', opacity: 0.7 },
      },
      {
        selector: 'node.focus',
        style: { 'border-width': 3, 'border-color': accent, width: 20, height: 20, 'font-weight': 'bold', 'z-index': 10 },
      },
      { selector: 'node:selected', style: { 'border-width': 3, 'border-color': accent } },
    ];
  }

  // create the instance once the container exists
  $effect(() => {
    const h = host;
    if (!h) return;
    let destroyed = false;
    let instance: Core | null = null;
    import('cytoscape').then(({ default: cytoscape }) => {
      if (destroyed) return;
      instance = cytoscape({
        container: h,
        style: style() as never,
        minZoom: 0.1,
        maxZoom: 4,
        wheelSensitivity: 0.3,
      });
      instance.on('tap', 'node', (ev) => {
        const d = ev.target.data() as { path?: string; line?: number };
        if (!d.path) return;
        navigate({ kind: 'file', study, sha, path: d.path, range: d.line ? { start: d.line } : undefined });
      });
      cy = instance;
    });
    return () => {
      destroyed = true;
      instance?.destroy();
      cy = null;
    };
  });

  // restyle on theme change
  $effect(() => {
    void themeState.dark;
    const c = cy;
    // CSS variables switch on the same tick; read them after the DOM update
    if (c) requestAnimationFrame(() => c.style(style() as never));
  });

  // (re)render elements when the selection changes
  $effect(() => {
    const c = cy;
    const sel = selection;
    const f = focus;
    if (!c || !sel) return;
    untrack(() => {
      const els: ElementDefinition[] = [
        ...sel.nodes.map((n) => ({
          group: 'nodes' as const,
          data: { id: n.id, label: n.label, color: colors.get(n.community) ?? '#888', path: n.path ?? undefined, line: n.line ?? undefined },
          classes: f && n.path === f ? 'focus' : '',
        })),
        ...sel.edges.map((e) => ({ group: 'edges' as const, data: { id: e.id, source: e.source, target: e.target } })),
      ];
      c.batch(() => {
        c.elements().remove();
        c.add(els);
      });
      const layout = c.layout({ name: 'cose', animate: false, randomize: true, nodeDimensionsIncludeLabels: true } as never);
      layout.one('layoutstop', () => {
        const focused = c.nodes('.focus');
        if (focused.length > 0) c.fit(focused, 120);
        else c.fit(undefined, 30);
      });
      layout.run();
    });
  });

  // keep the canvas sized to its container
  $effect(() => {
    const h = host;
    const c = cy;
    if (!h || !c) return;
    const ro = new ResizeObserver(() => c.resize());
    ro.observe(h);
    return () => ro.disconnect();
  });
</script>

<div class="graph">
  {#if model?.key !== key}
    <div class="empty">Cargando grafo…</div>
  {:else if model.error}
    <div class="empty">Error al cargar graph.json: {model.error}</div>
  {:else if !graph}
    <div class="empty">Este commit no tiene grafo (graph/graph.json).</div>
  {:else}
    <aside class="side">
      <input type="search" placeholder="Filtrar nodos…" bind:value={text} aria-label="Filtrar nodos" />
      <div class="all">
        <button onclick={() => setAll(true)}>todas</button>
        <button onclick={() => setAll(false)}>ninguna</button>
      </div>
      <ul class="communities">
        {#each graph.communities as c (c.id)}
          <li>
            <label>
              <input type="checkbox" checked={selected.has(c.id)} onchange={() => toggle(c.id)} />
              <span class="swatch" style="background: {c.color}"></span>
              <span class="cname" title={c.name}>{c.name}</span>
              <span class="count">{c.count}</span>
            </label>
          </li>
        {/each}
      </ul>
    </aside>
    <div class="stage">
      {#if selection && (selection.truncated || (focus && focusCount === 0))}
        <div class="notice">
          {#if selection.truncated}
            Se muestran {selection.nodes.length} de {selection.total} nodos (máximo {MAX_NODES}). Filtra por comunidad o texto para ver
            el resto.
          {/if}
          {#if focus && focusCount === 0}
            <span><code>{focus}</code> no tiene nodos en el grafo.</span>
          {/if}
        </div>
      {/if}
      {#if selection && selection.nodes.length === 0}
        <div class="empty overlay">Ningún nodo coincide con los filtros.</div>
      {/if}
      <div class="canvas" bind:this={host}></div>
    </div>
  {/if}
</div>

<style>
  .graph {
    display: flex;
    height: 100%;
    min-height: 0;
  }
  .side {
    flex: none;
    width: 200px;
    border-right: 1px solid var(--border);
    padding: 6px;
    display: flex;
    flex-direction: column;
    gap: 6px;
    overflow: auto;
  }
  .side input[type='search'] {
    width: 100%;
  }
  .all {
    display: flex;
    gap: 4px;
  }
  .all button {
    font-size: 12px;
    padding: 1px 6px;
  }
  .communities {
    list-style: none;
    margin: 0;
    padding: 0;
  }
  .communities label {
    display: flex;
    align-items: center;
    gap: 5px;
    padding: 2px 0;
    font-size: 13px;
    cursor: pointer;
  }
  .swatch {
    width: 10px;
    height: 10px;
    border-radius: 50%;
    flex: none;
  }
  .cname {
    flex: 1;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .count {
    color: var(--fg-muted);
    font-size: 11px;
  }
  .stage {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
    position: relative;
  }
  .notice {
    padding: 4px 10px;
    font-size: 12px;
    border-bottom: 1px solid var(--border);
    background: var(--bg-alt);
    color: var(--fg-muted);
    display: flex;
    gap: 12px;
  }
  .canvas {
    flex: 1;
    min-height: 0;
  }
  .overlay {
    position: absolute;
    inset: 40px 0 auto;
    text-align: center;
    pointer-events: none;
  }
</style>
