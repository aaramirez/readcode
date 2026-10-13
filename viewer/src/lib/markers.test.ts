import { describe, expect, it } from 'vitest';
import vectors from '../../../core/readcode/data/schemas/marker-vectors.json';
import { renderMarkdown } from './markdown';
import { parseMarkerBody, parseMarkers } from './markers';

interface Vector {
  name: string;
  input: string;
  expected: unknown[];
}

describe('marker grammar parity (core/readcode/data/schemas/marker-vectors.json, shared with pytest)', () => {
  it('has vectors', () => {
    expect((vectors as Vector[]).length).toBeGreaterThanOrEqual(30);
  });

  for (const v of vectors as Vector[]) {
    it(v.name, () => {
      expect(parseMarkers(v.input)).toEqual(v.expected);
    });
  }
});

describe('marker detection through the real markdown-it pipeline (reference behavior)', () => {
  // Code-detection vectors: the markers parseMarkers keeps must be exactly the ones markdown-it
  // renders as refs, so code spans / blocks are detected the same way on both sides.
  for (const v of (vectors as Vector[]).filter((x) => x.name.startsWith('código:'))) {
    it(v.name, () => {
      const html = renderMarkdown(v.input);
      const rendered = [...html.matchAll(/class="rc-ref[^"]*"[^>]*>([^<]*)</g)].map((m) => m[1]);
      const expected = (v.expected as { raw: string }[]).map((m) => m.raw);
      expect(rendered.length).toBe(expected.length);
      expect(parseMarkers(v.input).map((m) => m.raw)).toEqual(expected);
    });
  }
});

describe('parseMarkerBody', () => {
  it('parses a body without the surrounding source', () => {
    expect(parseMarkerBody('ref', 'a.py#f|x', '[[ref:a.py#f|x]]')).toEqual({
      kind: 'symbol',
      raw: '[[ref:a.py#f|x]]',
      path: 'a.py',
      symbol: 'f',
      range: null,
      label: 'x',
    });
    expect(parseMarkerBody('archify', 'a b', '[[archify:a b]]').kind).toBe('invalid');
  });
});
