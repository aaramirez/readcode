---
status: approved
date: 2026-10-12
---

# readcode v1 — núcleo, visor y skill

## Problem / Goal

Construir la v1 de readcode: una herramienta personal para estudiar repositorios de código. Un proceso previo (núcleo determinista en Python + skill de Claude Code) genera **estudios** en un directorio (p. ej. el repo privado `code-kb`); un visor web servido localmente (`readcode serve <dir>`) permite navegar árbol, código, explicaciones por bloque, referencias clicables con historial, diagramas Mermaid/Archify, grafo de Graphify, tours guiados y diffs explicados entre commits estudiados.

Diseño completo y aprobado: [`docs/superpowers/specs/2026-10-12-readcode-design.md`](../docs/superpowers/specs/2026-10-12-readcode-design.md). Este plan no repite el spec; lo ordena en pasos verificables.

## Approach

- **Datos separados de presentación**: formato de estudio en JSON/Markdown definido por JSON Schema (`schemas/`), contrato único entre generador y visor.
- **Lo mecánico es determinista** (Python, sin LLM): snapshot, índice tree-sitter, resolución de referencias, diff, validación, servidor.
- **Lo explicativo es del LLM** vía skill `/readcode` que orquesta el CLI y subagentes; todo lo que escribe pasa por `readcode validate`.
- **Visor SPA precompilado** (Vite + Svelte + TS), `dist/` versionado para no requerir Node al usar.

Descartados: visor sin build por CDN (mantenimiento y offline), sitio estático por estudio (no escala con varios commits ni permite "abrir cualquier directorio"), CLI con API de Anthropic (pospuesto a post-v1), SCIP (pospuesto).

Orden de construcción: **schemas → núcleo → estudio de ejemplo hecho a mano → visor → skill**. El estudio de ejemplo permite construir y probar el visor sin depender del skill.

## Architecture / Components

| Componente | Ubicación | Responsabilidad |
|---|---|---|
| Schemas | `schemas/*.schema.json` | Fuente de verdad del formato de estudio (`study`, `catalog`, `tree`, `symbols`, `explain`, `dir`, `tour`, `changes`, `diff-explain`, `issues`) |
| Núcleo | `core/readcode/` | CLI `readcode` (click/typer): `init`, `snapshot`, `index`, `plan`, `graph`, `diff`, `validate`, `catalog`, `serve` |
| Visor | `viewer/` | SPA Svelte; `viewer/dist/` empaquetado dentro del paquete Python para `serve` |
| Skill | `skills/readcode/` | `SKILL.md` + `prompts/{explain-file,dir,overview,tour,diff}.md` |
| Ejemplos | `examples/fixture-repo/`, `examples/kb/` | Repo multilenguaje de prueba (Py, TS, Go, SQL) con ≥2 commits + estudio generado |

## Data flow

```
repo git ──snapshot/index/graph──▶ <kb>/<estudio>/snapshots/<sha>/{tree,symbols,graph}
                                         │
                       plan ──lotes──▶ subagentes (skill) ──escriben──▶ explain/, dirs/, overview.md, tours/, diagrams/
                                         │
                                     validate ──errores──▶ subagentes (≤2 reintentos) ──resto──▶ issues.json
                                         │
                                     catalog ──▶ <kb>/catalog.json
                                         │
browser ◀── readcode serve <kb> ── viewer/dist + archivos del kb (bajo demanda)
```

## Configuration

`<kb>/<estudio>/study.json` (campos mínimos):

| Campo | Tipo | Significado |
|---|---|---|
| `schemaVersion` | int | Versión del formato (empieza en 1) |
| `name` | string | Id del estudio (nombre de carpeta) |
| `title` | string | Nombre legible |
| `repo` | `{url, localPath?}` | Origen del código |
| `language` | string | Idioma de las explicaciones (`es` por defecto) |
| `exclude` | string[] | Globs excluidos además de `.gitignore` y defaults |
| `tools` | `{graphify: bool, archify: bool}` | Disponibilidad en la última generación |
| `snapshots` | `[{sha, date, message, status}]` | `status`: `indexed` \| `explained` \| `partial` |

`<kb>/catalog.json`: `{schemaVersion, studies: [{name, title, repo, snapshots: n, updated}]}`.

Defaults de exclusión: `node_modules/`, `vendor/`, `dist/`, `build/`, `*.min.*`, lockfiles (`*.lock`, `package-lock.json`, `pnpm-lock.yaml`, `poetry.lock`, `go.sum`), binarios (detección por bytes nulos), archivos > 1 MB.

Resto de estructuras: sección 4 del spec.

## Implementation steps

### Fase 0 — Andamiaje

1. Estructura de carpetas del repo (`core/`, `viewer/`, `skills/`, `schemas/`, `examples/`), `README.md` mínimo, `.gitignore`, `LICENSE` (MIT).
2. `core/pyproject.toml` (Python ≥ 3.11; deps: `typer`, `jsonschema`, `tree-sitter`, `tree-sitter-language-pack`, `pathspec`; dev: `pytest`). Entry point `readcode`. Verificar: `pip install -e core[dev]` y `readcode --help`.
3. `examples/fixture-repo/`: script `make_fixture.py` que crea un repo git pequeño con archivos Python, TypeScript, Go y SQL, llamadas cruzadas, un nombre ambiguo a propósito, y **2 commits** (el segundo modifica, agrega y borra archivos). Verificar: `git log` del fixture muestra 2 commits.

### Fase 1 — Schemas

4. Escribir los JSON Schema en `schemas/`. Incluir ejemplos válidos e inválidos en `core/tests/data/schemas/`.
5. Módulo `readcode.schemas` que carga y valida; tests de ejemplos válidos/inválidos. Verificar: `pytest -k schemas`.

### Fase 2 — Núcleo

6. `readcode.io`: escritura atómica (temp + rename), helpers de rutas del kb, hash de blobs (sha256 del contenido). Tests.
7. `init`: crea `study.json` con defaults; falla si el estudio existe (salvo `--force`). Tests.
8. `snapshot`: `git archive <sha>` a temporal → aplica exclusiones (`.gitignore` vía `pathspec` + defaults + `exclude`) → escribe blobs deduplicados y `tree.json`; registra el snapshot en `study.json`. Test: dos snapshots del fixture comparten blobs sin cambio.
9. `index`: tree-sitter con tags queries por lenguaje → `symbols.json` (defs, refs, imports). Archivos no parseables → `indexed: false`. Tests por lenguaje del fixture.
10. Resolución de referencias (`readcode.refs`): parser de `[[ref:ruta#símbolo]]` / `[[ref:ruta:Lx-y]]` / `[[archify:nombre]]`; resolución mismo archivo → importados → global; resultado `exacta | ambigua(candidatos) | rota`. Tests con el nombre ambiguo del fixture.
11. `plan`: compara `tree.json` vs `explain/` existentes por `blobHash`; copia explicaciones de blobs sin cambio desde el snapshot anterior; emite JSON de lotes pendientes (archivos agrupados por directorio, con tamaño en líneas), directorios pendientes, y si faltan overview/tours. Tests: tras snapshot 2, solo los archivos cambiados quedan pendientes.
12. `graph`: ejecuta `graphify update` sobre el snapshot extraído y copia `graph.json`; si graphify no existe, marca `tools.graphify=false` y sale con aviso (no error). Test con graphify mockeado.
13. `diff`: genera `changes.json` (A/M/D + hunks con rangos en ambos lados) entre dos snapshots del estudio. Test con el fixture.
14. `validate`: schemas + rangos dentro del archivo + bloques sin solapes + refs resueltas + diagramas existentes. Salida legible y `--json` con `{file, problem, hint}` para el skill. Exit code ≠ 0 si hay errores. Tests con casos inválidos.
15. `catalog`: recorre el kb y escribe `catalog.json`. Test.
16. `serve`: `http.server` que sirve `viewer/dist` en `/` y el kb en `/kb/`; abre el browser (`--no-open` para desactivar). Test de humo con request a `/kb/catalog.json`.

### Fase 3 — Estudio de ejemplo

17. Generar con el núcleo el estudio del fixture en `examples/kb/fixture/` (ambos commits) y escribir **a mano** explicaciones, resúmenes de directorio, `overview.md` con un Mermaid, un tour, un diagrama Archify (o un HTML stub si Archify no está instalado) y la explicación del diff. Debe incluir al menos una ref ambigua. Verificar: `readcode validate` sin errores.

### Fase 4 — Visor

18. Scaffold `viewer/` (Vite + Svelte + TS, Vitest, Playwright). Script `npm run dev` que apunta al kb de ejemplo; `npm run build` escribe en `core/readcode/viewer_dist/` (empaquetado con el paquete Python).
19. Capa de datos (`lib/data.ts`): cliente fetch con caché para catalog, study, tree, symbols, explain, dirs, tours, diffs; manejo de 404 → "sin datos".
20. Router por hash (`#/<estudio>/<sha>/<ruta>:L42-78`, más rutas para overview, tour/paso, grafo, diff). Historial ← → en UI. Tests Vitest.
21. Layout de tres paneles redimensionables, barra superior (estudio, commit, comparar, ← →, búsqueda), tema claro/oscuro, UI en español.
22. Árbol de archivos con filtro, iconos por lenguaje y estado (excluido / con issues / A-M-D en modo diff). Selección de directorio → resumen en panel derecho.
23. Vista de código con CodeMirror 6 solo lectura; resaltado del bloque activo; decoración de símbolos clicables (Ctrl+clic → definición; menú "Ver usos").
24. Panel de explicación: render markdown-it con plugin para `[[ref]]` (enlace o menú de candidatos), `[[archify]]` (iframe sandbox) y Mermaid. Sincronía bidireccional bloque ↔ scroll. Tests Vitest del plugin y de la sincronía.
25. Pestaña Overview y pestaña Diagramas (lista de `diagrams/`).
26. Pestaña Grafo con Cytoscape: carga `graph.json`, filtro por comunidad, clic en nodo → archivo, botón "ver en grafo" desde el código. Oculta la pestaña si no hay grafo.
27. Tours: lista y reproductor paso a paso (◀ ▶, progreso), cada paso navega a archivo+rango con su narración.
28. Selector de commit (conserva archivo si existe) y vista de diff: CodeMirror merge lado a lado, explicación global y por hunk a la derecha.
29. Búsqueda Ctrl+K sobre archivos, símbolos y títulos de bloque.
30. Avisos: `issues.json` por archivo, `schemaVersion` incompatible, estudio incompleto.
31. Playwright e2e sobre `examples/kb`: árbol → archivo → ref → atrás → tour → cambiar commit → diff. Build final y commit de `dist`. Verificar: `readcode serve examples/kb` funciona sin Node.

### Fase 5 — Skill

32. `skills/readcode/SKILL.md`: subcomandos `study`, `update`, `diff`, `tour`; prerequisitos (readcode instalado, graphify/archify opcionales); flujo de 7 fases del spec §6; reglas (siempre validar, no commitear en el kb por su cuenta, reanudable vía `plan`).
33. Plantillas `prompts/`: `explain-file.md` (schema del bloque, convención `[[ref]]`, cuándo usar Mermaid, criterios de agrupación de bloques), `dir.md`, `overview.md` (incluye cómo invocar Archify), `tour.md`, `diff.md`. Todas en el idioma del estudio.
34. Script de instalación (`readcode install-skill` o instrucción en README) que copia el skill a `~/.claude/skills/readcode`.
35. Corrida end-to-end: `/readcode study examples/fixture-repo` en un kb temporal, luego `/readcode update` al segundo commit y `/readcode diff`. Verificar: `validate` limpio, revisión manual en el visor, y que `update` solo reexplica los archivos cambiados.

### Fase 6 — Cierre

36. README completo: instalación (`pipx install` desde el repo), instalación del skill, flujo con `code-kb`, capturas.
37. Corrida real sobre un repo mediano propio y anotar ajustes (tamaño de lotes, calidad de prompts) como issues para v1.1.

## Error handling

- Escritura atómica en todo el núcleo: un comando interrumpido nunca deja JSON parcial.
- `plan` es la fuente de "qué falta": cualquier fallo del skill se recupera re-ejecutando el subcomando.
- Errores de `validate` tras 2 reintentos → `issues.json`; el estudio se publica con avisos, no se descarta.
- Graphify/Archify ausentes → se omiten y se registra en `study.json`; el visor oculta lo que no existe.
- Archivos no parseables o lenguajes sin gramática → `indexed: false`; se pueden explicar igual pero sin refs de símbolo (solo por rango de líneas).
- Repos muy grandes: `plan` limita el tamaño de lote por líneas; el visor nunca carga más que el archivo actual + índices.

## Testing / validation

- `pytest` en `core/` (fases 1–2) en verde.
- `readcode validate examples/kb/fixture` sin errores.
- Vitest + Playwright en `viewer/` en verde.
- Corrida end-to-end del skill sobre el fixture (paso 35) y revisión manual en el visor.
- Corrida real sobre un repo mediano (paso 37).

## Out of scope

Runner por API de Anthropic, indexadores SCIP, edición de explicaciones desde el visor, multiusuario, publicación automática en Pages, CI de GitHub Actions (se puede agregar después).

## Open questions

- Si `readcode catalog` debe generar también un `README.md` en la raíz del kb (lista de estudios legible en GitHub).

## Decisiones posteriores a la propuesta

- El repo de estudios es `aaramirez/code-kb`, privado.
- Archify se instala globalmente (`npx skills add tt-a1i/archify -g`) como prerequisito; se usa también en otros proyectos. El skill igual degrada con aviso si no está disponible.
