import { describe, expect, it } from 'vitest';
import vectors from '../../../schemas/marker-vectors.json';
import { parseMarkerBody, parseMarkers } from './markers';

interface Vector {
  name: string;
  input: string;
  expected: unknown[];
}

describe('marker grammar parity (schemas/marker-vectors.json, shared with pytest)', () => {
  it('has vectors', () => {
    expect((vectors as Vector[]).length).toBeGreaterThanOrEqual(30);
  });

  for (const v of vectors as Vector[]) {
    it(v.name, () => {
      expect(parseMarkers(v.input)).toEqual(v.expected);
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
