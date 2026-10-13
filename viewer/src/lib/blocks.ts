// Block <-> code position helpers (pure).

import type { Block } from './types';

/**
 * Block to activate when `topLine` is the first visible code line: the block
 * whose range contains it (the innermost — latest start — if several do),
 * otherwise the nearest preceding block (latest end, then latest start);
 * null if every block is below.
 */
export function activeBlock(blocks: readonly Block[], topLine: number): string | null {
  let best: Block | null = null;
  for (const b of blocks) {
    if (b.range[0] <= topLine && topLine <= b.range[1]) {
      if (!best || b.range[0] > best.range[0] || (b.range[0] === best.range[0] && b.range[1] < best.range[1])) best = b;
    }
  }
  if (best) return best.id;
  for (const b of blocks) {
    if (b.range[1] < topLine) {
      if (!best || b.range[1] > best.range[1] || (b.range[1] === best.range[1] && b.range[0] > best.range[0])) best = b;
    }
  }
  return best ? best.id : null;
}

/** Block matching a navigated line range: exact range first, else the one active at its start. */
export function blockForRange(blocks: readonly Block[], start: number, end: number = start): string | null {
  const exact = blocks.find((b) => b.range[0] === start && b.range[1] === end);
  return exact ? exact.id : activeBlock(blocks, start);
}
