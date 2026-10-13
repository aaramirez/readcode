---
status: implemented
date: 2026-10-13
---

# readcode v1.1 — correcciones y pendientes de v1

## Problem / Goal

La v1 ([plan 0001](0001-readcode-v1.md), merge `ee74e52`) quedó funcional, pero las revisiones dejaron 15 pendientes. Algunos hacen que el visor muestre algo incorrecto (líneas desfasadas, referencias que abren el commit equivocado). Otros hacen que el visor muestre información tarde o incompleta, dejan huecos en las herramientas de la skill o complican el mantenimiento. Este plan los cierra todos sin cambiar el modelo del estudio. Solo hay cambios de formato compatibles hacia atrás, con migración explícita donde haga falta.

## Approach

- **Compatibilidad primero.** Un kb escrito por v1 tiene que seguir abriéndose y validando. Donde cambia el formato (la raíz de `dirs/`, `eolOnly`), el lector acepta lo viejo y `readcode migrate` lo reescribe.
- **El índice derivado se regenera solo.** Que tours, diagramas y búsqueda no aparezcan hasta correr `validate` era un problema de flujo, no del visor. `serve` detecta índices obsoletos y los regenera al arrancar. Se descartó listar directorios desde el visor, porque el servidor es estático y el kb puede servirse con otro servidor.
- **Paridad Python/TS por vectores.** Toda diferencia entre markdown-it y el detector de código de Python se fija con un caso nuevo en `marker-vectors.json` antes de tocar código.
- **Empaquetado real.** `schemas/` y `skills/` pasan a ser datos del paquete (`core/readcode/data/`) y se leen con `importlib.resources`. Se descartó un hook de build que los copie, porque agrega un paso fácil de olvidar y dos fuentes de verdad.

## Architecture / Components

| # | Mejora | Dónde |
|---|---|---|
| 1 | CodeMirror corta solo en `\n` | `viewer/src/components/CodeView.svelte`, `DiffView.svelte` |
| 2 | Referencia por línea que solo resuelve en A abre A | `core/readcode/validate_cmd.py` (diff links), `viewer/src/lib/data.ts` |
| 3 | Raíz de dirs sin colisión con una carpeta `_root` | `kbio.py`, `plan_cmd.py`, `stale_cmd.py`, `validate_cmd.py`, `ExplainPanel.svelte`, nuevo `migrate_cmd.py` |
| 4 | Re-snapshot con árbol distinto degrada el estado | `core/readcode/snapshot.py` |
| 5 | Los diagramas `.mmd` aparecen en la pestaña Diagramas | `validate_cmd.py` (los lista en links.json), `data.ts`, `DiagramsView.svelte` |
| 6, 7 | Tours, diagramas y `search.json` al día sin `validate` manual | `server.py` + `validate_cmd.py` (modo solo derivados) |
| 8 | Cambio solo de finales de línea marcado `eolOnly` | `diff_cmd.py`, `schemas/changes.schema.json`, `DiffPanel.svelte`, `prompts/diff.md` |
| 9 | `stale` cubre `[[ref::Lx-y]]` | `core/readcode/stale_cmd.py` |
| 10 | Paridad en la detección de código | `schemas/marker-vectors.json`, `refs.py`, `viewer/src/lib/markdown.ts` |
| 11 | Tours de kbs viejos funcionan sin re-validar | `viewer/src/lib/data.ts` (respaldo a la clave por tour) |
| 12 | Instalación no editable | `core/readcode/data/{schemas,skills}`, `schemas.py`, `install_skill.py`, `pyproject.toml` |
| 13 | `App.svelte` dividido | `viewer/src/App.svelte` → `lib/nav.ts` + componentes de layout |
| 14 | `readcode archify` | nuevo `archify_cmd.py`, `SKILL.md` |
| 15 | Gramáticas sin red | nuevo comando `readcode grammars` en `indexer.py` / `cli.py` |

## Configuration

- **Raíz de dirs.** El resumen de la raíz pasa de `snapshots/<sha>/dirs/_root.json` a `snapshots/<sha>/dir-root.json`, fuera de `dirs/`, donde no puede chocar con ninguna ruta del repo. Al leer, se acepta `dirs/_root.json` como raíz solo si `tree.json` no tiene una carpeta `_root`. `validate` emite un aviso `legacy-root` y `readcode migrate <kb> [study]` renombra el archivo.
- **`changes.json`.** Cada cambio puede llevar `eolOnly: true`, que significa que el archivo es modificado, sus hunks están vacíos y solo difieren los finales de línea. El campo es opcional en el schema, así que los kbs viejos siguen validando.
- **`links.json`.** Se agrega `diagrams: [{name, kind: "archify"|"mermaid"}]`, la lista explícita de lo que hay en `diagrams/`. El visor deja de deducirla de los marcadores, aunque si falta (kb viejo) sigue deduciéndola como en v1. En los diffs, cada referencia resuelta guarda `snapshot: "A"|"B"`, el lado contra el que resolvió.
- **`readcode serve`.** Regenera por defecto los derivados obsoletos al arrancar. Un estudio está obsoleto si algún archivo bajo `snapshots/` o `diffs/` es más nuevo que su `links.json`. `--no-refresh` desactiva la regeneración y deja `serve` de solo lectura, como en v1.
- **`readcode grammars [--fetch] [LANG...]`.** Sin `--fetch`, lista las gramáticas que están en caché. Con `--fetch`, descarga las indicadas, o todas las que usa `indexer.py` si no se indica ninguna.
- **`readcode archify <kb> <study> <sha> <name> <type> <input.json>`.** Busca `archify.mjs` en `~/.agents/skills/archify` o `~/.claude/skills/archify`, o en `$ARCHIFY_BIN` si está definido. Valida el nombre con la misma regla del marcador (`[A-Za-z0-9._-]`, sin `..`) y escribe `diagrams/<name>.html` y `diagrams/<name>.json`.

## Implementation steps

### Fase A — Correcciones de visualización

1. **CodeMirror con `\n`.** Agregar `EditorState.lineSeparator.of("\n")` a las extensiones de `CodeView.svelte` (las dos llamadas a `EditorState.create`, incluido el cálculo de doc de la línea 95) y de `DiffView.svelte`/merge view. Test en vitest: con el texto `"a\rb\nc"`, el editor tiene 2 líneas y la línea 2 es `c`.
2. **Diff refs del lado A.**
   - En `validate`, al resolver los links de un diff, guardar `snapshot: "A"` cuando la referencia solo resolvió en A, ya sea por línea o por símbolo, aunque el archivo exista en B.
   - El visor abre la referencia en el sha de A cuando `snapshot === "A"`.
   - Tests: en pytest, una referencia `path:L5-6` a líneas que solo existen en A queda con `snapshot: "A"`; en vitest, el router navega a A.
3. **`eolOnly`.**
   - `diff_cmd` marca `eolOnly: true` cuando los blobs difieren pero son iguales tras normalizar `\r\n` y `\r` a `\n`.
   - Actualizar `changes.schema.json`.
   - `DiffPanel` muestra la etiqueta "solo finales de línea".
   - `prompts/diff.md` indica no explicar esos archivos.
   - Test en pytest con dos blobs CRLF/LF.

### Fase B — Formato y migración

4. **Raíz de dirs.**
   - Cambiar `kbio.dir_doc_path("")` a `dir-root.json`.
   - Actualizar `plan_cmd`, `stale_cmd`, `validate_cmd`, `ExplainPanel.svelte` y `data.ts`.
   - Implementar la lectura compatible descrita en Configuration.
   - Crear `migrate_cmd.py` y el comando `readcode migrate`, idempotente.
   - Migrar `examples/kb/fixture`.
   - Tests:
     - Un repo con carpeta `_root` tiene dos resúmenes distintos.
     - Un kb viejo valida con el aviso `legacy-root` y queda limpio tras `migrate`.
5. **Re-snapshot.** Si `tree.json` ya existía y su lista de `(path, blob)` o su lista `excluded` cambia, el estado vuelve a `indexed` si había símbolos o a `partial` si no, y se imprime un aviso. Si el árbol no cambió, se mantiene el estado, como hoy. Test en pytest con las exclusiones cambiadas.
6. **Lista de diagramas.**
   - `validate` escribe `links.json.diagrams` a partir de `diagrams/*.html` (archify) y `diagrams/*.mmd` (mermaid).
   - `DiagramsView` renderiza los `.mmd` con el mismo componente mermaid de `Markdown.svelte`.
   - Si falta el campo, el visor usa la lista deducida, como en v1.
7. **Respaldo de claves de tour.** En `data.ts`, si no existe la clave `tours/<id>.json#<n>`, usar `tours/<id>.json`. Test en vitest con un `links.json` de v1.

### Fase C — Derivados al día

8. **Modo solo derivados.** Separar en `validate_cmd` la escritura de `links.json`, `issues.json` y `search.json` de la validación con schemas, y exponerla como `validate --derived-only`, que es más rápido y no falla por avisos.
9. **Regeneración en `serve`.**
   - Al arrancar, revisar el mtime de cada estudio y regenerar los obsoletos con el paso 8.
   - Registrar en consola qué estudios regeneró.
   - Agregar el flag `--no-refresh`.
   - Si la regeneración falla, avisar y servir lo que hay.
   - Test en pytest: tocar un tour y arrancar el servidor en un hilo; el `links.json` resultante incluye el tour.

### Fase D — Herramientas de la skill

10. **`stale` con referencias sin ruta.** Resolver `[[ref::Lx-y]]` contra el archivo dueño del documento: `explain/<path>.json` usa `<path>`, y en dirs, overview y tours no aplica, porque `validate` ya lo prohíbe ahí. Test: un archivo con líneas cambiadas y una referencia sin ruta a esas líneas aparece como obsoleto.
11. **Paridad en la detección de código.**
    - Agregar vectores para estos casos:
      - Bloque indentado con 4 espacios.
      - Fence `~~~`.
      - Fence con más backticks que el de cierre.
      - Fence sin cerrar.
      - Código inline con dos backticks que contiene un backtick.
      - Marcador dentro de HTML escapado.
    - Ajustar `refs.py` hasta que pytest y vitest pasen con los mismos vectores. El comportamiento de referencia es el de markdown-it.
12. **`readcode archify`.**
    - Implementar el comando con la búsqueda y la validación de Configuration.
    - Si `node` o Archify no están disponibles, termina con código 2 y un mensaje claro.
    - Reemplazar en `SKILL.md` la invocación directa de `archify.mjs` por `readcode archify`.
    - Test en pytest con un `ARCHIFY_BIN` falso: un script que escribe un HTML mínimo.
13. **`readcode grammars`.** Implementarlo sobre `tree_sitter_language_pack` (la lista de gramáticas sale del mapa de lenguajes de `indexer.py`). `index` sugiere `readcode grammars --fetch` cuando falla por falta de red. Test con la descarga mockeada.

### Fase E — Empaquetado y mantenimiento

14. **Datos dentro del paquete.**
    - Mover con `git mv` `schemas/` a `core/readcode/data/schemas/` y `skills/readcode/` a `core/readcode/data/skills/readcode/`.
    - `schemas.py` e `install_skill.py` pasan a usar `importlib.resources.files("readcode") / "data" / ...`.
    - En `pyproject.toml`, agregar `data/**` a package-data.
    - Actualizar las rutas de `markers.test.ts`, `types.ts`, `data.ts`, `README.md` y el spec, en los enlaces y en el texto.
    - Verificación manual: `pipx install ./core` en un venv limpio, luego `readcode init` + `validate examples/kb fixture` + `install-skill` en un directorio temporal.
    - Quitar del README la limitación de instalación.
15. **Dividir `App.svelte`.**
    - Extraer a `viewer/src/lib/nav.ts` el historial ← → y el estado de ruta, como un store de Svelte con tests unitarios.
    - Extraer a `components/Workspace.svelte` el layout de árbol, código y panel.
    - Extraer a `components/Shell.svelte` la barra superior y los atajos.
    - Meta: `App.svelte` con menos de 200 líneas.
    - Las pruebas e2e existentes deben pasar sin cambios.
16. **Cierre.**
    - Recompilar `core/readcode/viewer_dist`.
    - Correr `readcode migrate` + `validate` sobre `examples/kb`.
    - Correr las tres suites.
    - Actualizar el README: comandos nuevos, `serve --no-refresh` e instalación con `pipx`.

## Error handling

- **`migrate` interrumpido.** El renombrado usa la escritura atómica de `kbio`. Si se corta, queda o el archivo viejo o el nuevo, y la lectura compatible acepta ambos. Volver a correrlo es seguro.
- **Regeneración en `serve` sobre un kb de solo lectura**, por ejemplo un clon sin permisos: captura el error, avisa una vez y sirve los derivados existentes.
- **Empaquetado.** Si un test o el visor sigue apuntando a `schemas/` en la raíz, el build falla de forma visible. No se dejan copias en la raíz, para que no haya dos fuentes de verdad.
- **`eolOnly` en kbs viejos.** Los `changes.json` sin el campo se ven igual que en v1. Para recalcularlos hay que volver a correr `readcode diff`.

## Testing / validation

- Cada paso agrega su test: pytest para el núcleo y vitest para el visor. Los vectores de paridad cubren el paso 11.
- Al final: pytest, vitest, Playwright e2e, y `readcode validate examples/kb fixture` sin problemas.
- Hay dos verificaciones manuales:
  - La instalación con `pipx` en un entorno limpio (paso 14).
  - Abrir el visor sobre un archivo con `\r` sueltos y comprobar que las explicaciones caen en su línea (paso 1).

## Out of scope

- La corrida sobre un repo real (paso 37 del plan 0001) y la creación de `aaramirez/code-kb`. Siguen siendo decisión del usuario y no dependen de este plan.
- El resolvedor de referencias en TypeScript: `links.json` sigue siendo el único resolvedor.
- Vigilar cambios mientras `serve` está corriendo. Solo se regenera al arrancar.
- Publicar en PyPI.

## Open questions

- **Que `serve` escriba en el kb por defecto** cambia una garantía de v1, en la que `serve` era de solo lectura. La alternativa es dejarlo opcional con `--refresh`. Este plan propone activarlo por defecto.
