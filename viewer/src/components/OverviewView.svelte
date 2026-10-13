<script lang="ts">
  import type { StudyData } from '../lib/data';
  import Markdown from './Markdown.svelte';

  let { data, sha }: { data: StudyData; sha: string } = $props();

  const overview = $derived(data.overview(sha));
</script>

<div class="overview">
  {#await overview}
    <div class="empty">Cargando…</div>
  {:then text}
    {#if text === null}
      <div class="empty">Este commit no tiene overview todavía.</div>
    {:else}
      <Markdown source={text} />
    {/if}
  {:catch err}
    <div class="empty">Error al cargar el overview: {err.message}</div>
  {/await}
</div>

<style>
  .overview {
    padding: 8px 24px 24px;
    overflow: auto;
    height: 100%;
    max-width: 60rem;
  }
</style>
