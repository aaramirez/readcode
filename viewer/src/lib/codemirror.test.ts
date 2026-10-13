import { EditorState } from '@codemirror/state';
import { describe, expect, it } from 'vitest';
import { lineSeparator } from './codemirror';

describe('lineSeparator', () => {
  it('splits only on \n, so a lone \r does not shift line numbers', () => {
    const state = EditorState.create({ doc: 'a\rb\nc', extensions: [lineSeparator] });
    expect(state.doc.lines).toBe(2);
    expect(state.doc.line(2).text).toBe('c');
  });

  it('would split on a lone \r without it (why the extension exists)', () => {
    expect(EditorState.create({ doc: 'a\rb\nc' }).doc.lines).toBe(3);
  });
});
