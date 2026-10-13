import { describe, expect, it } from 'vitest';
import { activeBlock, blockForRange } from './blocks';
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
