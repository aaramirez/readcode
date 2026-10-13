// Lazy mermaid rendering for the `.rc-mermaid` placeholders emitted by
// lib/markdown.ts. mermaid is imported on first use (separate chunk).

type Mermaid = (typeof import('mermaid'))['default'];

let loader: Promise<Mermaid> | null = null;
let configuredTheme: string | null = null;
let seq = 0;
// mermaid keeps global config: serialize renders so a theme switch can't race.
let queue: Promise<unknown> = Promise.resolve();

function load(): Promise<Mermaid> {
  loader ??= import('mermaid').then((m) => m.default);
  loader.catch(() => (loader = null));
  return loader;
}

function showError(el: HTMLElement, source: string, message: string): void {
  el.replaceChildren();
  const warn = document.createElement('div');
  warn.className = 'rc-mermaid-error';
  warn.textContent = `No se pudo renderizar el diagrama Mermaid: ${message}`;
  const pre = document.createElement('pre');
  pre.textContent = source;
  el.append(warn, pre);
}

async function renderOne(el: HTMLElement, source: string, dark: boolean): Promise<void> {
  let mermaid: Mermaid;
  try {
    mermaid = await load();
  } catch (e) {
    return showError(el, source, (e as Error).message);
  }
  const theme = dark ? 'dark' : 'default';
  if (configuredTheme !== theme) {
    mermaid.initialize({ startOnLoad: false, securityLevel: 'strict', theme });
    configuredTheme = theme;
  }
  const id = `rc-mermaid-${++seq}`;
  try {
    await mermaid.parse(source);
    const { svg } = await mermaid.render(id, source);
    el.innerHTML = svg; // produced by mermaid with securityLevel "strict" (sanitized)
    el.dataset.rendered = theme;
  } catch (e) {
    document.getElementById(id)?.remove();
    document.getElementById('d' + id)?.remove();
    showError(el, source, (e as Error).message ?? String(e));
  }
}

/** Render every mermaid placeholder inside `root` (idempotent per theme). */
export function renderMermaidIn(root: HTMLElement, dark: boolean): void {
  const theme = dark ? 'dark' : 'default';
  for (const el of root.querySelectorAll<HTMLElement>('.rc-mermaid')) {
    if (el.dataset.rendered === theme) continue;
    el.dataset.source ??= el.querySelector('.rc-mermaid-src')?.textContent ?? '';
    const source = el.dataset.source;
    queue = queue.then(() => (el.isConnected ? renderOne(el, source, dark) : undefined));
  }
}
