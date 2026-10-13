# readcode — Diseño

- **Fecha:** 2026-10-12
- **Autor:** Alexander Ramírez (aramirez@grupoconex.net)
- **Estado:** Aprobado (pendiente de revisión del spec escrito)

## 1. Propósito

Herramienta personal para **entender y leer código fuente** de repositorios a los que se tiene acceso. Un proceso previo (LLM + scripts deterministas) genera un **estudio** de un repo; un **visor en el browser** permite navegarlo: árbol de directorios, código, explicaciones por bloque sincronizadas, referencias clicables con historial atrás/adelante, diagramas (Mermaid, Archify), grafo de Graphify, recorridos guiados y comparación entre commits estudiados.

### Criterios de éxito

1. Abrir `readcode serve <dir>` sobre un directorio con estudios y navegar cualquiera de ellos en el browser.
2. Al seleccionar un archivo se ve el código y, a la derecha, las explicaciones de sus bloques, sincronizadas con el scroll.
3. Las referencias en explicaciones y en el código llevan al punto correcto; ← → recorren el historial.
4. Se navega el grafo de Graphify, los diagramas de Archify y los Mermaid embebidos.
5. Se pueden estudiar varios commits del mismo repo, cambiar entre ellos y ver un diff explicado entre dos.
6. Funciona con repos grandes y multilenguaje.

## 2. Repositorios y despliegue

| Repo | Visibilidad | Contenido |
|---|---|---|
| `aaramirez/readcode` | Público | Núcleo Python, visor, skill de Claude Code, schemas, ejemplos |
| `code-kb` | Privado | Resultados: uno o más estudios, actualizados con el tiempo |

El visor no está atado a `code-kb`: recibe **cualquier directorio** provisto por el usuario (`readcode serve <dir>`). Quien clona `code-kb` y tiene `readcode` instalado ve los estudios.

## 3. Decisiones tomadas

| Tema | Decisión |
|---|---|
| Cómo se abre | Servidor local liviano (`readcode serve`), carga bajo demanda |
| Código en el estudio | Copia del código por commit (snapshot), almacenada por hash de contenido (dedupe) |
| Commits | Varios snapshots por estudio, navegables; diffs explicados entre pares |
| Generación | Núcleo determinista (Python) + skill de Claude Code para la parte LLM; runner por API fuera de v1 |
| Referencias | tree-sitter (tags queries), heurística transparente, candidatos múltiples si es ambiguo |
| Niveles de explicación | Bloques, resumen por archivo y directorio, visión general del repo, tours guiados |
| Cobertura | Todos los archivos fuente, excluyendo vendor/lockfiles/binarios/minificados/generados (configurable) |
| Idioma | Español por defecto, configurable por estudio; UI en español |
| Visor | SPA precompilada (Vite + Svelte + TS), datos JSON por archivo |

## 4. Formato del estudio (contrato generador ↔ visor)

La fuente de verdad es `schemas/` (JSON Schema). Estructura:

```
<kb-dir>/
  catalog.json                        lista de estudios (generado por `readcode catalog`)
  <estudio>/
    study.json                        schemaVersion, nombre, repo URL, idioma, reglas de exclusión,
                                      herramientas disponibles (graphify/archify),
                                      snapshots[] {sha, fecha, mensaje, estado}
    blobs/<h2>/<hash>.txt             contenido por hash (dedupe entre commits)
    snapshots/<sha>/
      tree.json                       {ruta → blob hash, lenguaje, líneas, indexed}
      symbols.json                    defs y refs {nombre, tipo, ruta, rango}
      explain/<ruta>.json             blobHash, resumen del archivo, bloques[]
      dirs/<ruta>.json                resumen por directorio
      overview.md                     visión general del repo
      tours/<id>.json                 {título, descripción, pasos[{ruta, rango, texto}]}
      graph/graph.json                salida de Graphify
      diagrams/<nombre>.html | .mmd   Archify (iframe) | Mermaid
      issues.json                     problemas no resueltos tras validación
    diffs/<shaA>..<shaB>/
      changes.json                    archivos agregados/modificados/borrados + hunks
      explain.md                      explicación global del cambio
      explain/<ruta>.json             explicación por archivo, por hunk
```

### Bloque

```json
{ "id": "b3", "range": [42, 78], "title": "Validación del token",
  "body": "Markdown con [[ref:src/auth/jwt.ts#verify]] y ```mermaid …```",
  "refs": [{ "symbol": "verify", "target": "src/auth/jwt.ts", "range": [10, 31] }] }
```

### Convenciones en Markdown

- `[[ref:ruta#símbolo]]` — referencia a un símbolo.
- `[[ref:ruta:L10-31]]` — referencia a un rango de líneas.
- `[[archify:nombre]]` — embebe `diagrams/nombre.html`.
- Bloques ```` ```mermaid ```` — diagrama Mermaid en línea.

### Reglas

- `explain/<ruta>.json` guarda el `blobHash` que explica: si el blob no cambia entre snapshots, la explicación se reutiliza sin LLM.
- El visor al arrancar solo lee `catalog.json` y `study.json`; el resto es bajo demanda.
- `schemaVersion` en `study.json` permite al visor detectar estudios incompatibles.

## 5. Núcleo determinista (`core/`, CLI `readcode`, Python)

Nunca llama a un LLM.

| Comando | Función |
|---|---|
| `readcode init <kb-dir> <estudio> --repo <path\|url>` | Crea `study.json`; reglas de exclusión desde `.gitignore` + defaults |
| `readcode snapshot <estudio> --sha <sha>` | `git archive` → blobs por hash + `tree.json` |
| `readcode index <estudio> --sha <sha>` | tree-sitter (`tree-sitter-language-pack`) → `symbols.json` |
| `readcode plan <estudio> --sha <sha>` | Qué falta explicar; lotes de trabajo; reutiliza por hash |
| `readcode graph <estudio> --sha <sha>` | `graphify update` (modo AST, sin LLM) sobre el snapshot → `graph/graph.json` |
| `readcode diff <estudio> <shaA> <shaB>` | `changes.json` |
| `readcode validate <estudio> [--sha]` | Schemas, rangos, `[[ref]]`, diagramas; errores en formato accionable para el skill |
| `readcode catalog <kb-dir>` | Regenera `catalog.json` |
| `readcode serve <kb-dir> [--port]` | Sirve `viewer/dist` + el directorio de estudios (`http.server`) |

### Resolución de referencias

Orden: mismo archivo → archivos importados (tags de import) → todo el repo. Si queda ambigua se guardan todos los candidatos; el visor muestra un menú. Las rotas se reportan en `validate`.

### Bloques

tree-sitter **sugiere** límites (funciones, clases); el LLM decide la agrupación final. `validate` solo verifica coherencia de rangos (dentro del archivo, sin solapes inválidos).

## 6. Skill de Claude Code (`skills/readcode/`)

Se instala en `~/.claude/skills/`. Orquesta el CLI; los subagentes escriben JSON/Markdown que luego pasa por `validate`. Plantillas en `prompts/` (`explain-file.md`, `dir.md`, `overview.md`, `tour.md`, `diff.md`) con el schema y ejemplos.

### Subcomandos

- `/readcode study <repo> [--sha] [--kb <dir>]`
- `/readcode update <estudio> [--sha HEAD]`
- `/readcode diff <estudio> <shaA> <shaB>`
- `/readcode tour <estudio> "<pregunta o flujo>"`

### Flujo de `study`

1. **Mecánica:** `init` → `snapshot` → `index` → `graph`.
2. **Archivos (paralelo):** `plan` reparte lotes agrupados por directorio; cada subagente recibe código, símbolos y vecinos en el grafo; escribe `explain/<ruta>.json`.
3. **Directorios (bottom-up):** resumen de cada directorio a partir de los de sus hijos.
4. **Overview + diagramas:** `overview.md` desde resúmenes de directorio + grafo; Archify genera diagramas de arquitectura y data flow en `diagrams/`.
5. **Tours:** se proponen 3–6 flujos principales (entrypoints, requests típicos, jobs); un subagente por tour siguiendo el grafo.
6. **Validación:** `validate`; errores vuelven al subagente (máx. 2 reintentos); lo restante va a `issues.json`.
7. **Cierre:** `catalog`; sugerir commit en el repo de estudios (no lo hace solo).

### `update` y `diff`

- `update`: nuevo snapshot; blobs sin cambio heredan explicación; se reexplican los cambiados y se regeneran los resúmenes de directorio afectados y el overview.
- `diff`: explicación global (intención del conjunto de cambios, usando los mensajes de commit entre A y B) + explicación por archivo modificado, por hunk.
- Todo es **reanudable**: `plan` calcula lo pendiente, así que re-ejecutar continúa donde quedó.

## 7. Visor (`viewer/`)

Stack: Vite + Svelte + TypeScript; CodeMirror 6 (solo lectura, decoraciones de rango, merge view); Mermaid; Cytoscape.js; markdown-it. `viewer/dist/` compilado y versionado para que `readcode serve` no requiera Node.

### Layout

```
┌ Estudio ▾ │ Commit ▾ │ Comparar… │ ← → │ Buscar Ctrl+K ┐
├───────────┬───────────────────────────┬─────────────────┤
│ Árbol     │ Código | Grafo | Diagramas│ Explicación     │
│ (filtro)  │ | Overview | Tours        │ (bloques, res., │
│           │                           │  diagramas)     │
└───────────┴───────────────────────────┴─────────────────┘
```

### Comportamiento

- **Router por hash:** `#/<estudio>/<sha>/<ruta>:L42-78`. ← → del navegador y de la UI son el historial; todo punto es enlazable.
- **Sincronía bidireccional:** scroll del código activa el bloque; clic en bloque salta al rango.
- **Referencias:** `[[ref]]` como enlaces; ambiguas → menú de candidatos. En el código, Ctrl+clic → definición; "Ver usos" desde `symbols.json`.
- **Directorio seleccionado:** muestra su resumen.
- **Grafo:** Cytoscape con filtro por comunidad; clic en nodo abre archivo; "ver en grafo" centra el archivo actual.
- **Diagramas:** Archify en `iframe` sandbox; Mermaid en línea.
- **Tours:** paso a paso ◀ ▶ con progreso; cada paso abre archivo + rango con su narración.
- **Commits:** el selector cambia de snapshot conservando el archivo si existe. "Comparar…" abre la vista de diff (lado a lado) con la explicación a la derecha y marca A/M/D en el árbol.
- **Búsqueda Ctrl+K:** archivos, símbolos y títulos de bloques (índice en cliente).
- Tema claro/oscuro, paneles redimensionables, estados vacíos explícitos (excluido, sin explicación, error de validación).

## 8. Manejo de errores

- Núcleo: escritura atómica (temporal + rename). Archivos no parseables o de lenguaje no soportado → `"indexed": false`, se continúa.
- Skill: fallos persistentes → `issues.json`; el visor los muestra como aviso en el archivo.
- Visor: tolera estudios incompletos (oculta pestañas sin datos); `schemaVersion` incompatible → mensaje claro.
- Graphify o Archify ausentes → el estudio se genera sin grafo o sin diagramas Archify; se anota en `study.json`.

## 9. Pruebas

- **Núcleo (pytest):** fixture multilenguaje (Python, TypeScript, Go, SQL); snapshot, index, resolución de refs (exacta/ambigua/rota), diff, reutilización por hash, `validate` con casos inválidos.
- **Visor:** Vitest (router, parser `[[ref]]`, sincronía bloque↔scroll); Playwright sobre el estudio de `examples/` (árbol → archivo → ref → atrás → tour → diff).
- **Skill:** corrida end-to-end sobre el fixture; criterio de aceptación: `validate` sin errores y revisión manual.

## 10. Estructura del repo `readcode`

```
readcode/
  core/            paquete Python `readcode` (CLI, indexer, validate, server)
  viewer/          Svelte + Vite; dist/ versionado
  skills/readcode/ SKILL.md + prompts/*.md
  schemas/         JSON Schema del formato de estudio
  examples/        repo fixture + estudio generado
  docs/            specs y planes
```

## 11. Fuera de alcance (v1)

- Runner por API de Anthropic (generación desatendida / CI).
- Indexadores precisos SCIP.
- Edición de explicaciones desde el visor.
- Multiusuario.
- Publicación automática en GitHub/GitLab Pages (el formato lo permite, no se automatiza).
