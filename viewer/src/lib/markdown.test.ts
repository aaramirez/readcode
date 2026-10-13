import { describe, expect, it } from 'vitest';
import { renderMarkdown, type MarkdownContext } from './markdown';
import type { Links } from './types';

const links: Links = {
  schemaVersion: 1,
  sha: 'a'.repeat(40),
  docs: {
    'explain/app/models.py.json': [
      { raw: '[[ref:app/main.py#main]]', kind: 'symbol', status: 'exact', target: 'app/main.py', range: [4, 7] },
      { raw: '[[ref::L2]]', kind: 'lines', status: 'exact', target: 'app/models.py', range: [2, 2] },
      {
        raw: '[[ref:#process]]',
        kind: 'symbol',
        status: 'ambiguous',
        candidates: [
          { target: 'app/services/auth.py', range: [5, 7] },
          { target: 'app/services/billing.py', range: [8, 10] },
        ],
      },
      { raw: '[[ref:app/x.py#gone]]', kind: 'symbol', status: 'broken' },
      { raw: '[[archify:missing]]', kind: 'archify', status: 'broken', target: 'diagrams/missing.html' },
      { raw: '[[archify:arquitectura]]', kind: 'archify', status: 'exact', target: 'diagrams/arquitectura.html' },
      // a hostile/garbled links.json: unsafe archify name marked exact, target with quotes and markup
      { raw: '[[archify:../x]]', kind: 'archify', status: 'exact', target: 'diagrams/../x.html' },
      { raw: '[[ref:evil.py#f]]', kind: 'symbol', status: 'exact', target: 'a"b<c>.py', range: [1, 2] },
    ],
  },
};

const ctx: MarkdownContext = {
  study: 'fixture',
  sha: '074ec965eabffb43a0224ef9f1426515d2818975',
  links,
  docKey: 'explain/app/models.py.json',
  diagramUrl: (name) => `kb/fixture/snapshots/074ec96/diagrams/${encodeURIComponent(name)}.html`,
};

function dom(html: string): string {
  return html.trim();
}

describe('renderMarkdown markers', () => {
  it('renders an exact ref as a link to the target range', () => {
    const html = renderMarkdown('ver [[ref:app/main.py#main]] aquí', ctx);
    expect(dom(html)).toBe(
      '<p>ver <a class="rc-ref rc-code" href="#/fixture/074ec965eabffb43a0224ef9f1426515d2818975/f/app/main.py:L4-7" ' +
        'title="app/main.py:L4-7">main</a> aquí</p>',
    );
  });

  it('opens ref targets in the snapshot chosen by shaFor (diff fallback to A)', () => {
    const A = 'a'.repeat(40);
    const withFallback: MarkdownContext = { ...ctx, shaFor: (t) => (t === 'app/main.py' ? A : ctx.sha) };
    expect(renderMarkdown('[[ref:app/main.py#main]]', withFallback)).toContain(`href="#/fixture/${A}/f/app/main.py:L4-7"`);
    const amb = renderMarkdown('[[ref:#process]]', withFallback);
    expect(amb).toContain(`#/fixture/${ctx.sha}/f/app/services/auth.py:L5-7`);
  });

  it('opens a ref marked snapshot "A" in snapshot A even if the file exists in B', () => {
    const A = 'a'.repeat(40);
    const l: Links = {
      ...links,
      docs: { 'explain.md': [{ raw: '[[ref:app/main.py:L5-6]]', kind: 'lines', status: 'exact', target: 'app/main.py', range: [5, 6], snapshot: 'A' }] },
    };
    const c: MarkdownContext = { ...ctx, links: l, docKey: 'explain.md', shaFor: (_t, snap) => (snap === 'A' ? A : ctx.sha) };
    expect(renderMarkdown('[[ref:app/main.py:L5-6]]', c)).toContain(`href="#/fixture/${A}/f/app/main.py:L5-6"`);
  });

  it('renders single-line and labelled refs', () => {
    expect(renderMarkdown('[[ref::L2]]', ctx)).toContain('href="#/fixture/074ec965eabffb43a0224ef9f1426515d2818975/f/app/models.py:L2"');
    expect(renderMarkdown('[[ref::L2]]', ctx)).toContain('>L2</a>');
    // labelled marker not in links.json -> broken, but shows the label
    expect(renderMarkdown('[[ref:app/main.py#main|la entrada]]', ctx)).toContain('>la entrada</span>');
  });

  it('renders an ambiguous ref as a button with escaped candidates', () => {
    const html = renderMarkdown('[[ref:#process]]', ctx);
    expect(html).toContain('<button type="button" class="rc-ref rc-code rc-ambiguous"');
    expect(html).toContain('title="Referencia ambigua: 2 candidatos">process</button>');
    const attr = /data-candidates="([^"]*)"/.exec(html)![1];
    const decoded = JSON.parse(attr.replace(/&quot;/g, '"').replace(/&amp;/g, '&'));
    expect(decoded).toEqual([
      { label: 'app/services/auth.py:L5-7', href: '#/fixture/074ec965eabffb43a0224ef9f1426515d2818975/f/app/services/auth.py:L5-7' },
      { label: 'app/services/billing.py:L8-10', href: '#/fixture/074ec965eabffb43a0224ef9f1426515d2818975/f/app/services/billing.py:L8-10' },
    ]);
  });

  it('renders broken, unknown and invalid refs as greyed spans', () => {
    expect(renderMarkdown('[[ref:app/x.py#gone]]', ctx)).toContain(
      '<span class="rc-ref rc-code rc-broken" title="referencia rota">gone</span>',
    );
    expect(renderMarkdown('[[ref:app/y.py#unknown]]', ctx)).toContain('title="referencia rota">unknown</span>');
    expect(renderMarkdown('[[ref:app/y.py]]', ctx)).toContain('title="marcador inválido">[[ref:app/y.py]]</span>');
    // without context nothing can be resolved
    expect(renderMarkdown('[[ref:app/main.py#main]]')).toContain('rc-broken');
  });

  it('does not touch markers in code spans or fences', () => {
    const html = renderMarkdown('`[[ref:app/main.py#main]]`\n\n```\n[[ref:app/main.py#main]]\n```', ctx);
    expect(html).not.toContain('rc-ref');
    expect(html).toContain('<code>[[ref:app/main.py#main]]</code>');
  });

  it('escapes attacker-controlled text', () => {
    const html = renderMarkdown('<script>x</script> [[ref:a.py#f|<img src=x onerror=alert(1)>]]', ctx);
    expect(html).not.toContain('<script>');
    expect(html).not.toContain('<img');
    expect(html).toContain('&lt;img src=x onerror=alert(1)&gt;');
  });

  it('renders archify markers as sandboxed lazy iframes, broken ones as notes', () => {
    const html = renderMarkdown('[[archify:arquitectura]]', ctx);
    expect(html).toContain(
      '<iframe sandbox="allow-scripts" loading="lazy" src="kb/fixture/snapshots/074ec96/diagrams/arquitectura.html" title="Diagrama arquitectura"></iframe>',
    );
    expect(html).toContain('target="_blank" rel="noopener">abrir en pestaña</a>');
    expect(renderMarkdown('[[archify:missing]]', ctx)).toContain('Diagrama no encontrado: <code>missing</code>');
  });

  it('wraps mermaid fences for lazy rendering, keeping the escaped source', () => {
    const html = renderMarkdown('```mermaid\nflowchart LR\n  a["<b>"] --> b\n```', ctx);
    expect(html).toContain('<div class="rc-mermaid"><pre class="rc-mermaid-src">flowchart LR\n  a[&quot;&lt;b&gt;&quot;] --&gt; b\n</pre></div>');
    expect(renderMarkdown('```python\nx = 1\n```')).toContain('<code class="language-python">');
  });

  it('works inside tables and lists', () => {
    const html = renderMarkdown('| a | b |\n|---|---|\n| x | [[ref:app/main.py#main]] |\n\n- [[ref:#process]]', ctx);
    expect(html).toContain('<td><a class="rc-ref rc-code"');
    expect(html).toContain('<li><button');
  });

  it('renders an archify marker missing from links.json as broken, not as an iframe', () => {
    const html = renderMarkdown('[[archify:otro]]', ctx);
    expect(html).not.toContain('<iframe');
    expect(html).toContain('Diagrama no encontrado: <code>otro</code>');
  });

  it('never embeds path-like archify names, even if links.json says exact', () => {
    for (const src of ['[[archify:../x]]', '[[archify:a/b]]', String.raw`[[archify:a\b]]`, '[[archify:a..b]]']) {
      const html = renderMarkdown(src, ctx);
      expect(html, src).not.toContain('<iframe');
      expect(html, src).not.toContain('href=');
    }
    // invalid by grammar -> greyed invalid marker
    expect(renderMarkdown('[[archify:../x]]', ctx)).toContain('title="marcador inválido">[[archify:../x]]</span>');
  });

  it('escapes links.json targets in href and title, and invalid archify names', () => {
    const html = renderMarkdown('[[ref:evil.py#f]]', ctx);
    expect(html).toContain('href="#/fixture/074ec965eabffb43a0224ef9f1426515d2818975/f/a%22b%3Cc%3E.py:L1-2"');
    expect(html).toContain('title="a&quot;b&lt;c&gt;.py:L1-2"');
    expect(html).not.toMatch(/<c>/);
    expect(renderMarkdown('[[archify:a&b]]', ctx)).toContain('>[[archify:a&amp;b]]</span>');
  });
});
