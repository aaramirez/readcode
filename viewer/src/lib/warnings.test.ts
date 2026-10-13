import { describe, expect, it } from 'vitest';
import { issuesByPath, warningCounts } from './warnings';
import type { Issue } from './types';

const PATHS = new Set(['app/main.py', 'app/services/billing.py', 'README.md']);

const issues: Issue[] = [
  { file: 'explain/app/main.py.json', problem: 'rango fuera del archivo', hint: 'corrige', source: 'validate' },
  { file: 'explain/app/main.py.json', problem: 'ref rota', source: 'validate' },
  { file: 'app/services/billing.py', problem: 'no se pudo generar', source: 'generator' },
  { file: 'dirs/app.json', problem: 'resumen vacío', source: 'validate' },
  { file: 'dir-root.json', problem: 'falta raíz', source: 'validate' },
  { file: 'dirs/_root.json', problem: 'raíz heredada', source: 'validate' },
  { file: 'tours/x.json', problem: 'tour roto', source: 'validate' },
  { problem: 'graphify falló', source: 'tool' },
];

describe('issuesByPath', () => {
  const r = issuesByPath(issues, PATHS);
  it('maps explain docs and plain repo paths to files', () => {
    expect(r.files.get('app/main.py')!.map((i) => i.problem)).toEqual(['rango fuera del archivo', 'ref rota']);
    expect(r.files.get('app/services/billing.py')).toHaveLength(1);
  });
  it('maps dir summaries to directories (root = "")', () => {
    expect(r.dirs.get('app')!.map((i) => i.problem)).toEqual(['resumen vacío']);
    expect(r.dirs.get('')!.map((i) => i.problem)).toEqual(['falta raíz', 'raíz heredada']);
  });
  it('treats dirs/_root.json as a real directory when the tree has a _root folder', () => {
    const e = issuesByPath(issues, new Set(['_root/a.py']));
    expect(e.dirs.get('_root')!.map((i) => i.problem)).toEqual(['raíz heredada']);
    expect(e.dirs.get('')!.map((i) => i.problem)).toEqual(['falta raíz']);
  });
  it('keeps the rest as general issues', () => {
    expect(r.other.map((i) => i.problem)).toEqual(['tour roto', 'graphify falló']);
  });
  it('handles an empty list', () => {
    const e = issuesByPath([], PATHS);
    expect(e.files.size + e.dirs.size + e.other.length).toBe(0);
  });
});

describe('warningCounts', () => {
  it('counts issues per file and per directory row', () => {
    const c = warningCounts(issuesByPath(issues, PATHS));
    expect(c.get('app/main.py')).toBe(2);
    expect(c.get('app/services/billing.py')).toBe(1);
    expect(c.get('app')).toBe(1);
    expect(c.has('')).toBe(false);
  });
});
