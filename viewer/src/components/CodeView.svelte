<script lang="ts">
  // Read-only CodeMirror view of one file: highlighting, folding, route range,
  // active block, Ctrl/Cmd+click on refs and "Ver usos" on definitions.
  // Scrolling reports the active block (no history entry); route changes
  // (:L ranges, block clicks) scroll the code.
  import { Compartment, EditorState } from '@codemirror/state';
  import { EditorView } from '@codemirror/view';
  import { onMount, untrack } from 'svelte';
  import { activeBlock, activeBlockAtBottom, blockForRange } from '../lib/blocks';
  import {
    bottomVisibleLine,
    codeViewExtensions,
    loadLanguage,
    setLineMarks,
    themeExtension,
    topVisibleLine,
    type RefSpan,
  } from '../lib/codemirror';
  import type { StudyData } from '../lib/data';
  import { format, navigate, type LineRange } from '../lib/router';
  import { findUsages, refOffset, resolveName } from '../lib/symbols';
  import { themeState } from '../lib/theme.svelte';
  import type { Block, Symbols, Tree } from '../lib/types';
  import CandidateMenu, { type MenuState } from './CandidateMenu.svelte';

  interface Props {
    data: StudyData;
    study: string;
    sha: string;
    tree: Tree;
    path: string;
    range?: LineRange;
    /** Active block id (shared with the explanation panel). */
    activeId: string | null;
    /** Bumped to re-reveal the same range (block clicked while already at its hash). */
    revealTick: number;
    onActive: (id: string | null) => void;
    /** Route of this file in the graph tab (null: no graph.json or the file has no nodes). */
    graphHref?: string | null;
  }

  let { data, study, sha, tree, path, range, activeId, revealTick, onActive, graphHref = null }: Props = $props();

  const file = $derived(tree.files.find((f) => f.path === path));
  const excluded = $derived(tree.excluded.find((e) => e.path === path));

  interface Loaded {
    key: string;
    text: string | null;
    blocks: Block[];
    symbols: Symbols | null;
    error?: string;
  }
  let loaded = $state<Loaded | null>(null);
  const key = $derived(`${study}@${sha}:${path}`);

  $effect(() => {
    const f = file;
    const k = key;
    const p = path;
    if (!f) return;
    Promise.all([
      data.blob(f.blob),
      data.explain(sha, p).catch(() => null),
      data.symbols(sha).catch(() => null),
    ]).then(
      ([text, explain, symbols]) => {
        if (key === k) loaded = { key: k, text, blocks: explain?.blocks ?? [], symbols };
      },
      (e: Error) => {
        if (key === k) loaded = { key: k, text: null, blocks: [], symbols: null, error: e.message };
      },
    );
  });
  const current = $derived(loaded?.key === key ? loaded : null);

  let host: HTMLElement | undefined = $state();
  let view: EditorView | null = null;
  let viewVersion = $state(0);
  let ignoreScrollUntil = 0;
  let menu = $state<MenuState | null>(null);
  const themeCompartment = new Compartment();
  const languageCompartment = new Compartment();

  function fileRoute(p: string, start: number, end?: number) {
    return { kind: 'file' as const, study, sha, path: p, range: { start, end: end === start ? undefined : end } };
  }

  // ---- create the editor for each loaded file
  $effect(() => {
    const c = current;
    const h = host;
    if (!c || c.text === null || !h) return;
    return untrack(() => {
      const doc = EditorState.create({ doc: c.text! }).doc;
      const fileSymbols = c.symbols?.files[path];
      const refs: RefSpan[] = [];
      for (const r of fileSymbols?.refs ?? []) {
        if (r.line < 1 || r.line > doc.lines) continue;
        const line = doc.line(r.line);
        const off = refOffset(line.text, r.col, r.name);
        if (off !== null) refs.push({ from: line.from + off, to: line.from + off + r.name.length, name: r.name });
      }
      refs.sort((a, b) => a.from - b.from);
      const defLines = new Map<number, string[]>();
      for (const d of fileSymbols?.defs ?? []) {
        defLines.set(d.range[0], [...(defLines.get(d.range[0]) ?? []), d.name]);
      }
      const symbols = c.symbols;
      const blocks = c.blocks;

      const v = new EditorView({
        parent: h,
        state: EditorState.create({
          doc,
          extensions: codeViewExtensions(doc, {
            dark: themeState.dark,
            themeCompartment,
            languageCompartment,
            refs,
            defLines,
            onRefClick: (ref, ev) => {
              const res = symbols ? resolveName(symbols, path, ref.name) : { status: 'broken' as const, candidates: [] };
              if (res.status === 'exact') {
                const d = res.candidates[0];
                navigate(fileRoute(d.path, d.def.range[0], d.def.range[1]));
                return;
              }
              menu = {
                x: ev.clientX,
                y: ev.clientY,
                title:
                  res.status === 'ambiguous'
                    ? `«${ref.name}»: ${res.candidates.length} definiciones posibles`
                    : `«${ref.name}»`,
                items: res.candidates.map((cand) => ({
                  label: `${cand.path}:L${cand.def.range[0]}-${cand.def.range[1]}`,
                  href: format(fileRoute(cand.path, cand.def.range[0], cand.def.range[1])),
                  detail: cand.def.parent ? `${cand.def.kind} de ${cand.def.parent}` : cand.def.kind,
                })),
                empty: 'No se encontró su definición en el repositorio.',
              };
            },
            onDefClick: (line, ev) => {
              const defs = (fileSymbols?.defs ?? []).filter((d) => d.range[0] === line);
              const items = defs.flatMap((d) =>
                (symbols ? findUsages(symbols, path, d) : []).map((u) => ({
                  label: `${u.path}:${u.line}`,
                  href: format(fileRoute(u.path, u.line)),
                  detail: [defs.length > 1 ? d.name : '', u.ambiguous ? 'ambigua' : ''].filter(Boolean).join(' · ') || undefined,
                })),
              );
              menu = {
                x: ev.clientX,
                y: ev.clientY,
                title: `Usos de ${defs.map((d) => `«${d.name}»`).join(', ')}`,
                items,
                empty: 'Sin usos en el repositorio.',
              };
            },
          }),
        }),
      });
      view = v;

      let frame = 0;
      const onScroll = () => {
        if (performance.now() < ignoreScrollUntil || frame) return;
        frame = requestAnimationFrame(() => {
          frame = 0;
          if (view !== v) return;
          const s = v.scrollDOM;
          const atBottom = s.scrollTop > 0 && s.scrollTop + s.clientHeight >= s.scrollHeight - 2;
          const top = topVisibleLine(v);
          onActive(atBottom ? activeBlockAtBottom(blocks, top, bottomVisibleLine(v)) : activeBlock(blocks, top));
        });
      };
      v.scrollDOM.addEventListener('scroll', onScroll, { passive: true });

      const lang = file?.language ?? null;
      loadLanguage(lang).then(
        (ext) => {
          if (view === v && ext) v.dispatch({ effects: languageCompartment.reconfigure(ext) });
        },
        () => {
          /* plain text fallback */
        },
      );

      viewVersion++;
      return () => {
        cancelAnimationFrame(frame);
        v.scrollDOM.removeEventListener('scroll', onScroll);
        v.destroy();
        if (view === v) view = null;
      };
    });
  });

  // ---- theme
  $effect(() => {
    const dark = themeState.dark;
    viewVersion;
    view?.dispatch({ effects: themeCompartment.reconfigure(themeExtension(dark)) });
  });

  // ---- route range: highlight + scroll + activate its block
  $effect(() => {
    const r = range;
    revealTick;
    viewVersion;
    const v = view;
    const c = current;
    if (!v || !c) return;
    untrack(() => {
      if (!r) {
        onActive(activeBlock(c.blocks, topVisibleLine(v)));
        return;
      }
      const lines = v.state.doc.lines;
      const start = Math.min(Math.max(1, r.start), lines);
      ignoreScrollUntil = performance.now() + 300;
      v.dispatch({ effects: EditorView.scrollIntoView(v.state.doc.line(start).from, { y: 'start', yMargin: 2 }) });
      onActive(blockForRange(c.blocks, r.start, r.end ?? r.start));
    });
  });

  // ---- line decorations (route range + active block)
  $effect(() => {
    const r = range;
    const id = activeId;
    viewVersion;
    const v = view;
    const block = current?.blocks.find((b) => b.id === id);
    v?.dispatch({
      effects: setLineMarks.of({
        range: r ? [r.start, r.end ?? r.start] : null,
        block: block ? block.range : null,
      }),
    });
  });

  // ---- Ctrl/Cmd held: emphasize clickable refs
  onMount(() => {
    const set = (e: KeyboardEvent) => view?.dom.classList.toggle('rc-mod', e.ctrlKey || e.metaKey);
    const clear = () => view?.dom.classList.remove('rc-mod');
    window.addEventListener('keydown', set);
    window.addEventListener('keyup', set);
    window.addEventListener('blur', clear);
    return () => {
      window.removeEventListener('keydown', set);
      window.removeEventListener('keyup', set);
      window.removeEventListener('blur', clear);
    };
  });

  const REASONS: Record<string, string> = {
    gitignore: '.gitignore',
    default: 'exclusiones por defecto',
    study: 'reglas del estudio',
    binary: 'archivo binario',
    size: 'tamaño mayor a 1 MB',
  };
</script>

<div class="code">
  <div class="header">
    <span class="path">{path}</span>
    {#if file}<span class="meta">{file.language ?? 'texto'} · {file.lines} líneas</span>{/if}
    {#if current?.symbols?.files[path]}
      <span class="hint">Ctrl+clic en un identificador: ir a la definición · ◇ en el margen: ver usos</span>
    {/if}
    {#if graphHref}
      <a class="graph-link" href={graphHref} title="Centrar este archivo en el grafo">ver en grafo</a>
    {/if}
  </div>
  {#if excluded}
    <div class="empty">Archivo excluido del estudio ({REASONS[excluded.reason] ?? excluded.reason}).</div>
  {:else if !file}
    <div class="empty">El archivo no existe en este commit.</div>
  {:else if !current}
    <div class="empty">Cargando…</div>
  {:else if current.error}
    <div class="empty">Error al cargar el archivo: {current.error}</div>
  {:else if current.text === null}
    <div class="empty">No se encontró el contenido del archivo.</div>
  {:else}
    {#key current.key}
      <div class="editor" bind:this={host}></div>
    {/key}
  {/if}
</div>
{#if menu}
  <CandidateMenu {menu} onClose={() => (menu = null)} />
{/if}

<style>
  .code {
    display: flex;
    flex-direction: column;
    height: 100%;
    min-height: 0;
  }
  .header {
    display: flex;
    gap: 12px;
    align-items: baseline;
    padding: 6px 10px;
    border-bottom: 1px solid var(--border);
    font-family: var(--font-code);
    font-size: 12px;
    white-space: nowrap;
    overflow: hidden;
  }
  .meta,
  .hint {
    color: var(--fg-muted);
  }
  .hint {
    font-family: var(--font-ui);
    margin-left: auto;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .graph-link {
    font-family: var(--font-ui);
    margin-left: auto;
    flex: none;
  }
  .hint + .graph-link {
    margin-left: 0;
  }
  .editor {
    flex: 1;
    min-height: 0;
  }
</style>
