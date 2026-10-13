<script lang="ts">
  // Vertical drag handle between two panes; reports horizontal deltas in px.
  let { onDrag, onEnd }: { onDrag: (dx: number) => void; onEnd?: () => void } = $props();

  let lastX: number | null = null;

  function down(e: PointerEvent) {
    lastX = e.clientX;
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
    e.preventDefault();
  }

  function move(e: PointerEvent) {
    if (lastX === null) return;
    onDrag(e.clientX - lastX);
    lastX = e.clientX;
  }

  function up() {
    if (lastX === null) return;
    lastX = null;
    onEnd?.();
  }
</script>

<div
  class="splitter"
  role="separator"
  aria-orientation="vertical"
  onpointerdown={down}
  onpointermove={move}
  onpointerup={up}
  onpointercancel={up}
></div>

<style>
  .splitter {
    flex: none;
    width: 5px;
    cursor: col-resize;
    background: var(--border);
    background-clip: content-box;
    padding: 0 2px;
    touch-action: none;
  }
  .splitter:hover {
    background-color: var(--accent);
    padding: 0 1px;
  }
</style>
