<script lang="ts" module>
  export interface MenuItem {
    label: string;
    /** Hash route; items without href are informative only. */
    href?: string;
    detail?: string;
  }

  export interface MenuState {
    x: number;
    y: number;
    title: string;
    items: MenuItem[];
    empty?: string;
  }
</script>

<script lang="ts">
  // Small floating menu (ambiguous refs, Ctrl+click candidates, "Ver usos").
  // Items are plain hash links, so choosing one is a normal history navigation.
  import { onMount } from 'svelte';

  let { menu, onClose }: { menu: MenuState; onClose: () => void } = $props();

  let el: HTMLElement | undefined = $state();
  let pos = $state({ left: 0, top: 0 });

  $effect(() => {
    const m = menu;
    const box = el;
    if (!box) return;
    const w = box.offsetWidth;
    const h = box.offsetHeight;
    pos = {
      left: Math.max(4, Math.min(m.x, window.innerWidth - w - 4)),
      top: m.y + h + 4 > window.innerHeight ? Math.max(4, m.y - h - 4) : m.y + 4,
    };
  });

  onMount(() => {
    const onDown = (e: MouseEvent) => {
      if (el && !el.contains(e.target as Node)) onClose();
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    // Capture so the opening click (already dispatched) does not close it.
    window.addEventListener('mousedown', onDown, true);
    window.addEventListener('keydown', onKey);
    window.addEventListener('blur', onClose);
    return () => {
      window.removeEventListener('mousedown', onDown, true);
      window.removeEventListener('keydown', onKey);
      window.removeEventListener('blur', onClose);
    };
  });
</script>

<div class="menu" role="menu" bind:this={el} style="left: {pos.left}px; top: {pos.top}px">
  <div class="title">{menu.title}</div>
  {#if menu.items.length === 0}
    <div class="none">{menu.empty ?? 'Sin resultados.'}</div>
  {:else}
    <ul>
      {#each menu.items as item, i (i)}
        <li>
          {#if item.href}
            <a role="menuitem" href={item.href} onclick={onClose}>{item.label}</a>
          {:else}
            <span>{item.label}</span>
          {/if}
          {#if item.detail}<span class="detail">{item.detail}</span>{/if}
        </li>
      {/each}
    </ul>
  {/if}
</div>

<style>
  .menu {
    position: fixed;
    z-index: 100;
    min-width: 220px;
    max-width: min(520px, 90vw);
    max-height: 50vh;
    overflow: auto;
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: 6px;
    box-shadow: 0 6px 24px rgba(0, 0, 0, 0.18);
    padding: 4px 0;
    font-size: 13px;
  }
  .title {
    padding: 4px 10px 6px;
    color: var(--fg-muted);
    border-bottom: 1px solid var(--border);
    font-weight: 600;
  }
  ul {
    list-style: none;
    margin: 0;
    padding: 2px 0;
  }
  li {
    display: flex;
    gap: 8px;
    align-items: baseline;
    padding: 0 10px;
  }
  li:hover {
    background: var(--bg-hover);
  }
  a,
  li > span:first-child {
    font-family: var(--font-code);
    padding: 3px 0;
    flex: 1;
    overflow-wrap: anywhere;
  }
  .detail {
    color: var(--fg-muted);
    font-size: 12px;
    white-space: nowrap;
  }
  .none {
    padding: 6px 10px;
    color: var(--fg-muted);
  }
</style>
