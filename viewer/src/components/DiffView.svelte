<script lang="ts">
  // Center of the diff view: side-by-side @codemirror/merge of one changed file
  // (A = old blob, B = new blob; added → empty A, deleted → empty B).
  // `focus` (bumped by clicking a hunk in the panel) scrolls to and marks that hunk.
  import { MergeView } from '@codemirror/merge';
  import { Compartment } from '@codemirror/state';
  import { EditorView } from '@codemirror/view';
  import { untrack } from 'svelte';
  import { editorText, loadLanguage, mergeSideExtensions, setLineMarks, themeExtension } from '../lib/codemirror';
  import type { StudyData } from '../lib/data';
  import { hunkTarget, type DiffBadge } from '../lib/diff';
  import { themeState } from '../lib/theme.svelte';
  import type { ChangedFile } from '../lib/types';

  interface Props {
    data: StudyData;
    a: string;
    b: string;
    change: ChangedFile;
    badge?: DiffBadge;
    language: string | null;
    /** Hunk to reveal; `tick` changes on every click so the same hunk can be revealed again. */
    focus: { index: number; tick: number } | null;
  }

  let { data, a, b, change, badge, language, focus }: Props = $props();

  const key = $derived(`${a}..${b}:${change.path}`);
  let loaded = $state<{ key: string; old: string; new: string; error?: string } | null>(null);
  $effect(() => {
    const k = key;
    const c = change;
    const none = Promise.resolve<string | null>('');
    Promise.all([c.fromBlob ? data.blob(c.fromBlob) : none, c.toBlob ? data.blob(c.toBlob) : none]).then(
      ([oldText, newText]) => {
        if (key !== k) return;
        if (oldText === null || newText === null) {
          loaded = { key: k, old: '', new: '', error: 'No se encontró el contenido (blob) de una de las versiones.' };
        } else loaded = { key: k, old: oldText, new: newText };
      },
      (e: Error) => {
        if (key === k) loaded = { key: k, old: '', new: '', error: e.message };
      },
    );
  });
  const current = $derived(loaded?.key === key ? loaded : null);

  let host: HTMLElement | undefined = $state();
  let merge = $state<MergeView | null>(null);
  const themeA = new Compartment();
  const themeB = new Compartment();
  const langA = new Compartment();
  const langB = new Compartment();

  $effect(() => {
    const c = current;
    const h = host;
    if (!c || c.error || !h) return;
    return untrack(() => {
      const dark = themeState.dark;
      const mv = new MergeView({
        a: { doc: editorText(c.old), extensions: mergeSideExtensions(dark, themeA, langA) },
        b: { doc: editorText(c.new), extensions: mergeSideExtensions(dark, themeB, langB) },
        parent: h,
        gutter: true,
        highlightChanges: true,
      });
      merge = mv;
      loadLanguage(language).then(
        (ext) => {
          if (merge !== mv || !ext) return;
          mv.a.dispatch({ effects: langA.reconfigure(ext) });
          mv.b.dispatch({ effects: langB.reconfigure(ext) });
        },
        () => {},
      );
      return () => {
        mv.destroy();
        if (merge === mv) merge = null;
      };
    });
  });

  $effect(() => {
    const dark = themeState.dark;
    const mv = merge;
    if (!mv) return;
    mv.a.dispatch({ effects: themeA.reconfigure(themeExtension(dark)) });
    mv.b.dispatch({ effects: themeB.reconfigure(themeExtension(dark)) });
  });

  // reveal + mark the focused hunk
  $effect(() => {
    const f = focus;
    const mv = merge;
    if (!mv) return;
    untrack(() => {
      const target = f ? hunkTarget(change.hunks[f.index]) : null;
      for (const side of ['a', 'b'] as const) {
        mv[side].dispatch({ effects: setLineMarks.of({ range: target?.side === side ? target.range : null, block: null }) });
      }
      if (!target) return;
      const view: EditorView = mv[target.side];
      const lines = view.state.doc.lines;
      if (lines === 0) return;
      const line = view.state.doc.line(Math.min(Math.max(1, target.range[0]), lines));
      view.dispatch({ effects: EditorView.scrollIntoView(line.from, { y: 'start', yMargin: 40 }) });
    });
  });
</script>

<div class="diff">
  <div class="header">
    <span class="side">
      A · {a.slice(0, 7)}
      {#if change.status === 'added'}<em>(no existía)</em>{:else}<code>{change.oldPath ?? change.path}</code>{/if}
    </span>
    <span class="side">
      B · {b.slice(0, 7)}
      {#if change.status === 'deleted'}<em>(eliminado)</em>{:else}<code>{change.path}</code>{/if}
      {#if badge}<span class="badge diff-{badge.badge}" title={badge.title}>{badge.badge}</span>{/if}
    </span>
  </div>
  {#if !current}
    <div class="empty">Cargando…</div>
  {:else if current.error}
    <div class="empty">Error: {current.error}</div>
  {:else}
    {#key current.key}
      <div class="merge" bind:this={host}></div>
    {/key}
  {/if}
</div>

<style>
  .diff {
    display: flex;
    flex-direction: column;
    height: 100%;
    min-height: 0;
  }
  .header {
    display: flex;
    border-bottom: 1px solid var(--border);
    font-size: 12px;
    flex: none;
  }
  .side {
    flex: 1;
    padding: 5px 10px;
    display: flex;
    gap: 6px;
    align-items: baseline;
    overflow: hidden;
    white-space: nowrap;
  }
  .side + .side {
    border-left: 1px solid var(--border);
  }
  .side em {
    color: var(--fg-muted);
  }
  .badge {
    font-family: var(--font-code);
    font-weight: 700;
    font-size: 10px;
    padding: 0 5px;
    border-radius: 8px;
    color: var(--accent-fg);
  }
  .diff-A {
    background: var(--added);
  }
  .diff-M {
    background: var(--warn);
  }
  .diff-D {
    background: var(--danger);
  }
  .diff-R {
    background: var(--accent);
  }
  .merge {
    flex: 1;
    min-height: 0;
  }
  .merge :global(.cm-mergeView) {
    height: 100%;
    overflow-y: auto;
  }
  .merge :global(.cm-mergeView .cm-editor) {
    height: auto;
  }
</style>
