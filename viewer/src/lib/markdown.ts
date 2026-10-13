// Markdown rendering (basic for now; Task 10 adds [[ref]] markers and mermaid).
import MarkdownIt from 'markdown-it';

const md = new MarkdownIt({ html: false, linkify: true });

export function renderMarkdown(src: string): string {
  return md.render(src);
}
