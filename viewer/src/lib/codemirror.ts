// CodeMirror 6 setup for the read-only code view: languages (lazy-loaded),
// theme, and the decorations driven by the viewer (route range, active block,
// symbol refs, definition gutter).

import { defaultHighlightStyle, foldGutter, codeFolding, syntaxHighlighting, foldKeymap } from '@codemirror/language';
import {
  Compartment,
  EditorState,
  RangeSet,
  StateEffect,
  StateField,
  Text,
  type Extension,
  type Range as CmRange,
} from '@codemirror/state';
import {
  Decoration,
  EditorView,
  GutterMarker,
  gutter,
  gutterLineClass,
  keymap,
  lineNumbers,
  type DecorationSet,
} from '@codemirror/view';
import { oneDarkHighlightStyle } from '@codemirror/theme-one-dark';

/** Language support for a tree.json language; null = plain text. */
export async function loadLanguage(language: string | null): Promise<Extension | null> {
  switch (language) {
    case 'python':
      return (await import('@codemirror/lang-python')).python();
    case 'javascript':
    case 'jsx':
    case 'typescript':
    case 'tsx': {
      const { javascript } = await import('@codemirror/lang-javascript');
      return javascript({ typescript: language.startsWith('t'), jsx: language.endsWith('x') });
    }
    case 'go':
      return (await import('@codemirror/lang-go')).go();
    case 'sql':
      return (await import('@codemirror/lang-sql')).sql();
    case 'java':
      return (await import('@codemirror/lang-java')).java();
    case 'json':
      return (await import('@codemirror/lang-json')).json();
    case 'markdown':
      return (await import('@codemirror/lang-markdown')).markdown();
    case 'html':
      return (await import('@codemirror/lang-html')).html();
    case 'css':
      return (await import('@codemirror/lang-css')).css();
    case 'yaml':
      return (await import('@codemirror/lang-yaml')).yaml();
    default:
      return null;
  }
}

/** Highlight style + dark flag; swapped through a compartment when the theme changes. */
export function themeExtension(dark: boolean): Extension {
  return [
    syntaxHighlighting(dark ? oneDarkHighlightStyle : defaultHighlightStyle, { fallback: true }),
    EditorView.darkTheme.of(dark),
  ];
}

// Colors come from the app's CSS variables, so light/dark follows app.css.
const baseTheme = EditorView.theme({
  '&': { height: '100%', backgroundColor: 'var(--code-bg)', color: 'var(--fg)' },
  '&.cm-focused': { outline: 'none' },
  '.cm-scroller': { fontFamily: 'var(--font-code)', fontSize: '13px', lineHeight: '1.5' },
  '.cm-content': { caretColor: 'transparent' },
  '.cm-gutters': { backgroundColor: 'var(--code-bg)', color: 'var(--fg-faint)', borderRight: '1px solid var(--border)' },
  '.cm-line.cm-rc-block': { backgroundColor: 'var(--bg-block)' },
  '.cm-line.cm-rc-range': { backgroundColor: 'var(--bg-highlight)' },
  '.cm-lineNumbers .cm-gutterElement.cm-rc-block-gutter': {
    boxShadow: 'inset -3px 0 var(--accent)',
    color: 'var(--fg)',
  },
  '.cm-rc-ref': { cursor: 'pointer', textDecorationLine: 'underline', textDecorationStyle: 'dotted', textDecorationColor: 'var(--fg-faint)' },
  '&.rc-mod .cm-rc-ref': { textDecorationStyle: 'solid', textDecorationColor: 'var(--accent)' },
  '.cm-rc-defs .cm-gutterElement': { padding: '0 2px', cursor: 'pointer', color: 'var(--fg-faint)' },
  '.cm-rc-defs .cm-gutterElement:hover': { color: 'var(--accent)' },
});

// ---------------------------------------------------------------- line marks

export interface LineMarks {
  /** Route range (:L42-78). */
  range: [number, number] | null;
  /** Active block range. */
  block: [number, number] | null;
}

export const setLineMarks = StateEffect.define<LineMarks>();

class BlockGutterClass extends GutterMarker {
  elementClass = 'cm-rc-block-gutter';
}
const blockGutterClass = new BlockGutterClass();

interface MarksValue {
  marks: LineMarks;
  decos: DecorationSet;
  gutter: RangeSet<GutterMarker>;
}

function lineStarts(state: EditorState, r: [number, number] | null): number[] {
  if (!r) return [];
  const doc = state.doc;
  const out: number[] = [];
  for (let n = Math.max(1, r[0]); n <= Math.min(r[1], doc.lines); n++) out.push(doc.line(n).from);
  return out;
}

function buildMarks(state: EditorState, marks: LineMarks): MarksValue {
  const decos: CmRange<Decoration>[] = [];
  for (const from of lineStarts(state, marks.block)) decos.push(Decoration.line({ class: 'cm-rc-block' }).range(from));
  for (const from of lineStarts(state, marks.range)) decos.push(Decoration.line({ class: 'cm-rc-range' }).range(from));
  const gutterMarks = lineStarts(state, marks.block).map((from) => blockGutterClass.range(from));
  return { marks, decos: Decoration.set(decos, true), gutter: RangeSet.of(gutterMarks, true) };
}

const lineMarksField = StateField.define<MarksValue>({
  create: (state) => buildMarks(state, { range: null, block: null }),
  update(value, tr) {
    let marks = value.marks;
    for (const e of tr.effects) if (e.is(setLineMarks)) marks = e.value;
    return marks === value.marks && !tr.docChanged ? value : buildMarks(tr.state, marks);
  },
  provide: (f) => [EditorView.decorations.from(f, (v) => v.decos), gutterLineClass.from(f, (v) => v.gutter)],
});

// ---------------------------------------------------------------- symbols

export interface RefSpan {
  from: number;
  to: number;
  name: string;
}

class DefMarker extends GutterMarker {
  constructor(readonly names: string) {
    super();
  }
  eq(other: GutterMarker): boolean {
    return other instanceof DefMarker && other.names === this.names;
  }
  toDOM(): Node {
    const span = document.createElement('span');
    span.textContent = '◇';
    span.title = `Ver usos de ${this.names}`;
    return span;
  }
}

export interface CodeViewOptions {
  dark: boolean;
  themeCompartment: Compartment;
  languageCompartment: Compartment;
  refs: RefSpan[];
  /** 1-based lines where definitions start, with their names. */
  defLines: Map<number, string[]>;
  /** Ctrl/Cmd+click on a ref. */
  onRefClick: (ref: RefSpan, event: MouseEvent) => void;
  /** Click on a definition marker in the "usos" gutter. */
  onDefClick: (line: number, event: MouseEvent) => void;
}

/** Extensions of the read-only code view. */
export function codeViewExtensions(doc: Text, o: CodeViewOptions): Extension[] {
  const refDecos = Decoration.set(
    o.refs.map((r) => Decoration.mark({ class: 'cm-rc-ref', attributes: { title: 'Ctrl+clic: ir a la definición' } }).range(r.from, r.to)),
    true,
  );
  const defMarkers = RangeSet.of(
    [...o.defLines.entries()]
      .filter(([line]) => line >= 1 && line <= doc.lines)
      .map(([line, names]) => new DefMarker(names.join(', ')).range(doc.line(line).from)),
    true,
  );
  return [
    EditorState.readOnly.of(true),
    EditorView.editable.of(false),
    lineNumbers(),
    gutter({
      class: 'cm-rc-defs',
      markers: () => defMarkers,
      initialSpacer: () => new DefMarker(''),
      domEventHandlers: {
        mousedown(view, line, event) {
          const n = view.state.doc.lineAt(line.from).number;
          if (!o.defLines.has(n)) return false;
          o.onDefClick(n, event as MouseEvent);
          return true;
        },
      },
    }),
    foldGutter(),
    codeFolding(),
    keymap.of(foldKeymap),
    baseTheme,
    o.themeCompartment.of(themeExtension(o.dark)),
    o.languageCompartment.of([]),
    lineMarksField,
    EditorView.decorations.of(refDecos),
    EditorView.domEventHandlers({
      mousedown(event, view) {
        if (event.button !== 0 || !(event.ctrlKey || event.metaKey)) return false;
        const pos = view.posAtCoords({ x: event.clientX, y: event.clientY });
        if (pos === null) return false;
        const ref = o.refs.find((r) => r.from <= pos && pos <= r.to);
        if (!ref) return false;
        event.preventDefault();
        o.onRefClick(ref, event);
        return true;
      },
    }),
  ];
}

/** First (mostly) visible line of the view. */
export function topVisibleLine(view: EditorView): number {
  const top = view.scrollDOM.getBoundingClientRect().top + 4;
  const block = view.lineBlockAtHeight(top - view.documentTop);
  return view.state.doc.lineAt(block.from).number;
}
