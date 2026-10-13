import { EditorState } from '@codemirror/state';
import { describe, expect, it } from 'vitest';
import { editorText, lineSeparator } from './codemirror';

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

describe('editorText', () => {
  it('turns CRLF into LF but keeps a lone \r inside its line', () => {
    const state = EditorState.create({ doc: editorText('a\r\nb\rc\n'), extensions: [lineSeparator] });
    expect(state.doc.lines).toBe(3); // a | b\rc | (empty after the final \n)
    expect(state.doc.line(1).text).toBe('a');
    expect(state.doc.line(2).text).toBe('b\rc');
    const noFinal = EditorState.create({ doc: editorText('a\r\nb\rc'), extensions: [lineSeparator] });
    expect(noFinal.doc.lines).toBe(2);
  });
});
