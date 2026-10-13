<script lang="ts">
  // A standalone mermaid diagram (diagrams/<name>.mmd), rendered with the same
  // strict-security pipeline as the mermaid blocks of Markdown.svelte.
  import type { StudyData } from '../lib/data';
  import { renderMermaidSource } from '../lib/mermaid';
  import { themeState } from '../lib/theme.svelte';

  let { data, sha, name }: { data: StudyData; sha: string; name: string } = $props();

  let host: HTMLElement | undefined = $state();
  let error = $state<string | null>(null);

  $effect(() => {
    const el = host;
    const dark = themeState.dark;
    if (!el) return;
    error = null;
    let cancelled = false;
    data.diagramSource(sha, name).then((src) => {
      if (cancelled) return;
      if (src === null) error = `No existe diagrams/${name}.mmd en este commit.`;
      else void renderMermaidSource(el, src, dark);
    });
    return () => {
      cancelled = true;
    };
  });
</script>

{#if error}
  <div class="error">{error}</div>
{/if}
<div class="host" bind:this={host}></div>

<style>
  .host {
    flex: 1;
    overflow: auto;
    padding: 12px;
  }
  .error {
    margin: 16px;
    padding: 10px 12px;
    border: 1px solid var(--danger);
    border-radius: 6px;
    color: var(--fg);
  }
</style>
