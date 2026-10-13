import { describe, expect, it } from 'vitest';
import { activeBlock, activeBlockAtBottom, blockForRange } from './blocks';
import type { Block } from './types';

const b = (id: string, start: number, end: number): Block => ({ id, range: [start, end], title: id, body: '' });

const blocks = [b('b1', 3, 10), b('b2', 12, 20), b('b3', 14, 16), b('b4', 30, 40)];

describe('activeBlock', () => {
  it('returns null before the first block and for no blocks', () => {
    expect(activeBlock(blocks, 1)).toBeNull();
    expect(activeBlock([], 5)).toBeNull();
  });

  it('returns the block containing the line (inclusive bounds)', () => {
    expect(activeBlock(blocks, 3)).toBe('b1');
    expect(activeBlock(blocks, 10)).toBe('b1');
    expect(activeBlock(blocks, 12)).toBe('b2');
    expect(activeBlock(blocks, 20)).toBe('b2');
  });

  it('prefers the innermost block when ranges nest', () => {
    expect(activeBlock(blocks, 15)).toBe('b3');
    expect(activeBlock(blocks, 17)).toBe('b2');
  });

  it('falls back to the nearest preceding block in gaps and after the last one', () => {
    expect(activeBlock(blocks, 11)).toBe('b1');
    expect(activeBlock(blocks, 25)).toBe('b2');
    expect(activeBlock(blocks, 99)).toBe('b4');
  });

  it('does not depend on block order', () => {
    expect(activeBlock([...blocks].reverse(), 15)).toBe('b3');
    expect(activeBlock([...blocks].reverse(), 25)).toBe('b2');
  });
});

describe('blockForRange', () => {
  it('prefers an exact range match, else the block active at the start', () => {
    expect(blockForRange(blocks, 12, 20)).toBe('b2');
    expect(blockForRange(blocks, 14, 16)).toBe('b3');
    expect(blockForRange(blocks, 13)).toBe('b2');
    expect(blockForRange(blocks, 1, 2)).toBeNull();
  });
});

describe('activeBlockAtBottom', () => {
  const tail = [b('b1', 1, 1), b('b2', 4, 5), b('b3', 8, 10), b('b4', 13, 15)];

  it('activates the last block whose start is visible', () => {
    expect(activeBlock(tail, 10)).toBe('b3'); // what the top line alone would give
    expect(activeBlockAtBottom(tail, 10, 15)).toBe('b4');
    expect(activeBlockAtBottom(tail, 6, 12)).toBe('b3');
  });

  it('prefers the innermost block when several start on the same line', () => {
    expect(activeBlockAtBottom([b('o', 5, 20), b('i', 5, 7)], 1, 30)).toBe('i');
  });

  it('falls back to the top-line rule when no block starts in view', () => {
    expect(activeBlockAtBottom(tail, 14, 15)).toBe('b4');
    expect(activeBlockAtBottom(tail, 11, 12)).toBe('b3');
    expect(activeBlockAtBottom([], 1, 9)).toBeNull();
  });
});
