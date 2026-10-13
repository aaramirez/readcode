<script lang="ts">
  import { renderMarkdown } from '../lib/markdown';

  let { source }: { source: string } = $props();
</script>

<!-- markdown-it runs with html: false, so raw HTML in the source is escaped. -->
<div class="markdown">{@html renderMarkdown(source)}</div>
