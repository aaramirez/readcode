<script lang="ts" module>
  import type { StudyData } from '../lib/data';
  import type { Links } from '../lib/types';

  /** Where a markdown doc lives, for marker resolution (see lib/markdown.ts). */
  export interface MdDoc {
    data: StudyData;
    study: string;
    /** Snapshot whose files the refs point to and whose diagrams are embedded. */
    sha: string;
    /** links.json doc key, e.g. "overview.md", "explain/app/main.py.json". */
    docKey: string;
    /** links.json to use (defaults to the snapshot's). */
    links?: Promise<Links | null>;
  }
</script>

<script lang="ts">
  import { readCandidates, renderMarkdown } from '../lib/markdown';
  import { renderMermaidIn } from '../lib/mermaid';
  import { themeState } from '../lib/theme.svelte';
  import CandidateMenu, { type MenuState } from './CandidateMenu.svelte';

  let { source, doc }: { source: string; doc?: MdDoc } = $props();

  // links.json is cached by StudyData; wait for it so markers don't flash as broken.
  let loaded = $state<{ key: string; links: Links | null } | null>(null);
  const linksKey = $derived(doc ? `${doc.study}@${doc.sha}` : '');
  $effect(() => {
    const d = doc;
    const key = linksKey;
    if (!d) return;
    (d.links ?? d.data.links(d.sha)).then(
      (links) => (loaded = { key, links }),
      () => (loaded = { key, links: null }),
    );
  });

  const html = $derived.by(() => {
    if (!doc) return renderMarkdown(source);
    if (loaded?.key !== linksKey) return null;
    const d = doc;
    return renderMarkdown(source, {
      study: d.study,
      sha: d.sha,
      links: loaded.links,
      docKey: d.docKey,
      diagramUrl: (name) => d.data.diagramUrl(d.sha, name),
    });
  });

  let root: HTMLElement | undefined = $state();
  $effect(() => {
    const dark = themeState.dark;
    if (html !== null && root) renderMermaidIn(root, dark);
  });

  let menu = $state<MenuState | null>(null);
  function onclick(e: MouseEvent) {
    const btn = (e.target as Element).closest?.('.rc-ambiguous');
    if (!btn) return;
    e.preventDefault();
    e.stopPropagation();
    const r = btn.getBoundingClientRect();
    menu = {
      x: r.left,
      y: r.bottom,
      title: `«${btn.textContent}» es ambigua: elige destino`,
      items: readCandidates(btn).map((c) => ({ label: c.label, href: c.href })),
    };
  }
</script>

<!-- markdown-it runs with html: false; marker elements carry escaped attributes only. -->
{#if html === null}
  <div class="markdown loading">Cargando…</div>
{:else}
  {#key html}
    <!-- svelte-ignore a11y_click_events_have_key_events, a11y_no_static_element_interactions -->
    <div class="markdown" bind:this={root} {onclick}>{@html html}</div>
  {/key}
{/if}
{#if menu}
  <CandidateMenu {menu} onClose={() => (menu = null)} />
{/if}

<style>
  .loading {
    color: var(--fg-muted);
  }
</style>
