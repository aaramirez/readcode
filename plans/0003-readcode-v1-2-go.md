---
status: approved
date: 2026-10-13
---

# readcode v1.2: Go, contexto de los subagentes y seguridad pendiente

## Problem / Goal

El primer estudio real, de `fibex-ai-harness` (Go, 177 archivos), funcionó: validó sin problemas y quedó en `explained`. Pero mostró huecos que bajan la calidad de las explicaciones en repos Go:

1. **Imports de Go sin resolver.** `indexer.py` deja `resolved: null` en todos los imports de Go (`internal/...` → `None`). Por eso `importedBy` y `usedBy` salen vacíos en `readcode context`, y las referencias sin ruta se saltan el nivel "archivos importados" y caen directo a "todo el repo".
2. **Mismo paquete invisible.** En Go, los archivos de una carpeta comparten paquete sin importarse. Una referencia `#Foo` desde `a.go` a `b.go` del mismo paquete no tiene un nivel propio.
3. **Variables y constantes de paquete no indexadas** (`var ErrSandboxUnavailable = ...`, `const StatusX = ...`). Los subagentes tuvieron que enlazarlas por rango de líneas.
4. **El contexto no trae las definiciones de los vecinos.** `readcode context` da las definiciones del propio archivo y las aristas del grafo (`runCmd() -> calls app.go#New()`), pero no las de los archivos de los que depende. Varios subagentes mencionaron funciones en texto, sin enlazarlas.
5. **Codificación en Windows.** Un subagente leyó un blob UTF-8 como si fuera otra codificación y escribió que el archivo tenía los acentos corruptos, lo cual era falso. Otro explicó secciones de un Markdown largo solo por sus títulos.
6. **Seguridad pendiente de v1.1** (dos hallazgos aparcados en la revisión final del plan 0002):
   - `kbio.resolve_sha` y `plan_cmd.reuse_source` aceptan shas que no son de 40 caracteres hexadecimales.
   - `readcode archify` sigue un enlace simbólico plantado bajo `snapshots/`.

## Approach

- **Go se resuelve por carpeta, no por archivo.** Un import de Go apunta a un paquete, que es una carpeta. Se lee `go.mod` (la línea `module`) para mapear `<module>/<subruta>` a la carpeta del repo, y el import gana un campo opcional `resolvedDir`. `resolved` (un archivo) sigue en `null`, así que el schema solo agrega un campo opcional y los estudios v1 siguen validando.
  - **Descartado:** forzar `resolved` a "un archivo representativo" del paquete. Es arbitrario, y los marcadores resolverían al archivo equivocado.
- **El nivel "importados" se expande a archivos.** Al resolver referencias (`refs.py`) y calcular `importedBy`/`usedBy` (`context_cmd.py`), un `resolvedDir` cuenta como todos los archivos `.go` de esa carpeta. No entran las subcarpetas, porque en Go no son el mismo paquete.
  - **Tests:** los archivos `_test.go` se incluyen solo si el archivo que importa también es un test. Un archivo normal no puede usar símbolos de un test.
- **Nuevo nivel "mismo paquete" para Go.** El orden de resolución queda así: el archivo actual, después los otros `.go` de su carpeta, después los importados y al final todo el repo. Los demás lenguajes no cambian.
- **Contexto con definiciones de los vecinos.** `readcode context` agrega `neighbourDefs`: las definiciones exportadas o de nivel superior de los archivos importados y de los del mismo paquete. Lleva un tope (40 por archivo y 200 en total) para no inflar el mensaje. Con eso, el subagente puede enlazar `[[ref:internal/app/app.go#App.Start]]` sin abrir otro archivo.
- **Prompts más estrictos.** `explain-file.md`, `dir.md`, `overview.md` y `tour.md` piden:
  - Leer los blobs como UTF-8.
  - No afirmar nunca problemas de codificación del archivo.
  - Leer completo cada archivo antes de explicarlo, en partes si es largo, en vez de explicar por los títulos.
  - Comprobar los marcadores contra `symbols.json`, como ya hacían por iniciativa propia los subagentes de directorios.
- **Seguridad: una sola validación central.**
  - `kbio.snapshot_dir`, `kbio.resolve_sha` y la lectura de shas en `plan_cmd` rechazan todo lo que no cumpla `^[0-9a-f]{40}$` y lo que no resuelva dentro de `<estudio>/snapshots`.
  - `validate_cmd._safe_snapshot_dir` y `archify_cmd._find_snapshot_dir` pasan a usar ese mismo helper, así que la protección contra enlaces simbólicos queda en un solo lugar.

## Architecture / Components

| # | Cambio | Dónde |
|---|---|---|
| 1 | Lectura de `go.mod` y `resolvedDir` en imports de Go | `core/readcode/indexer.py` (`_build_imports`, nuevo `_go_module`/`_resolve_go`), `data/schemas/symbols.schema.json`, `viewer/src/lib/types.ts` |
| 2 | Variables y constantes de paquete en Go | `core/readcode/queries/go.scm`, `indexer.py` (solo `var_spec`/`const_spec` de nivel superior; kinds `variable`/`constant`, que ya están en el enum) |
| 3 | Niveles "mismo paquete" e "importados por carpeta" | `core/readcode/refs.py` (`resolve`, línea ~286), con vectores nuevos en un test de resolución |
| 4 | `importedBy`/`usedBy` con carpetas, y `neighbourDefs` | `core/readcode/context_cmd.py` (`file_context`, `format_context`) |
| 5 | Prompts más estrictos | `core/readcode/data/skills/readcode/prompts/{explain-file,dir,overview,tour}.md`, `SKILL.md` (mensaje tipo del subagente) |
| 6 | Validación central de shas | `core/readcode/kbio.py` (nuevo `safe_snapshot_dir`), `plan_cmd.py`, `validate_cmd.py`, `archify_cmd.py`, y los comandos que usan `resolve_sha` |

## Data flow

```
go.mod ──module path──▶ indexer: import "github.com/x/y/internal/app" ──▶ resolvedDir "internal/app"
                                                                         │
         refs.resolve: archivo → mismo paquete → archivos de resolvedDir → repo
         context: importedBy/usedBy por carpeta; neighbourDefs de importados + mismo paquete
```

## Configuration

- **`symbols.json`:** cada import puede llevar `resolvedDir` (string, ruta de carpeta relativa a la raíz con `/`, o ausente). Es opcional y lo leen solo el núcleo y el visor.
- **`go.mod`:** se toma el de la raíz del repo. Si no existe, o hay varios módulos (`go.work` o `go.mod` anidados), se usa el `go.mod` más cercano hacia arriba de cada archivo. Si tampoco hay ninguno, no se resuelve nada, igual que hoy.
- **`readcode context --json`:** campo nuevo `neighbourDefs: ["<ruta>#<nombre> (<kind>) Lx-y", ...]`, con un tope de 40 por archivo vecino y 200 en total; se marca `truncated: true` si se recorta.

## Implementation steps

1. **`go.mod` y `resolvedDir`.**
   - Parsear `module <ruta>` del `go.mod` aplicable, con soporte de módulos anidados.
   - Para cada import con el prefijo del módulo, quitar el prefijo y aceptar la carpeta solo si existe en `tree.json` y contiene al menos un `.go`.
   - Agregar el campo al schema y a `types.ts`.
   - Tests:
     - Con `module github.com/x/y`, el import `github.com/x/y/internal/app` da `resolvedDir: "internal/app"`.
     - Los imports de la librería estándar y externos quedan sin resolver.
     - Un módulo anidado resuelve contra su propio `go.mod`.
2. **Variables y constantes de paquete.**
   - Agregar a `go.scm` `var_spec` y `const_spec` con el filtro de nivel superior en `indexer.py`; las declaraciones dentro de funciones no se indexan.
   - Cubrir los bloques `var ( ... )` y `const ( ... )`: cada nombre es un def con el rango de su línea.
   - Test con `ErrX = errors.New(...)` y un bloque `const` con `iota`.
3. **Resolución en `refs.py`.** Niveles para Go, en este orden: el archivo, el mismo paquete (los otros `.go` de su carpeta, con los `_test.go` solo si el actual es test), los archivos de cada `resolvedDir`, y todo el repo. Tests:
   - `#Foo` definido en otro archivo del mismo paquete resuelve exacto, aunque exista otro `Foo` en otro paquete.
   - `#Foo` de un paquete importado gana a uno del repo.
   - Python, JS y Java siguen dando los resultados de hoy (regresión).
4. **`readcode context`.**
   - Calcular `importedBy`/`usedBy` también con `resolvedDir`: un archivo `x.go` cuenta como importado por quien importe su carpeta.
   - Agregar `neighbourDefs` con sus topes y mostrarlo en `format_context`.
   - Tests sobre un mini repo Go en un fixture temporal.
5. **Prompts.** Agregar las reglas de UTF-8, de lectura completa y de comprobar marcadores, y explicar el uso de `neighbourDefs` en `explain-file.md` ("enlaza los símbolos de los vecinos con `[[ref:ruta#Nombre]]` o `#Clase.método`"). En `SKILL.md`, agregar al mensaje tipo una línea "Lee los blobs como UTF-8". El test de contenido de la skill (`test_skill.py`) se amplía.
6. **Validación central de shas.**
   - `kbio.safe_snapshot_dir(sdir, sha)` valida el formato y que la ruta resuelta tenga como padre `<sdir>/snapshots`.
   - `kbio.resolve_sha` filtra los shas de `study.json` con el mismo formato.
   - `plan_cmd.reuse_source` y sus lecturas del snapshot anterior usan el helper.
   - `validate_cmd._safe_snapshot_dir` y `archify_cmd._find_snapshot_dir` lo reutilizan; el caso del junction o enlace simbólico ya tiene repro en la revisión de v1.1.
   - Tests:
     - `study.json` con un sha absoluto o con `../`: `plan` no copia nada de fuera.
     - Un junction de 40 hex bajo `snapshots/`: `archify` termina con código 2.
7. **Reindexar el ejemplo y cerrar.**
   - Regenerar `examples/kb`. El fixture tiene Go (`examples/fixture-repo`), así que `symbols.json` cambia.
   - Correr `validate`, compilar `viewer_dist` si cambió `types.ts`, y correr pytest, vitest y e2e.
   - README: comentar que Go resuelve por paquete y documentar `neighbourDefs`.
8. **Verificación sobre el estudio real.**
   - En el kb `code-kb`, correr `readcode index` sobre el snapshot `1fbf419` de `fibex-ai-harness` y después `readcode validate`.
   - Comprobar que `readcode context ... cmd/fibex-ai/main.go` da `internal/app` como importado, con `neighbourDefs` que incluyan `App.Start`.
   - Comprobar que las explicaciones existentes siguen validando: los símbolos nuevos no rompen referencias, solo agregan.
   - No se vuelve a explicar nada. Sugerir el commit en el kb.

## Error handling

- **`go.mod` ilegible o sin la línea `module`:** se avisa una vez por estudio en `index` y los imports de Go quedan sin resolver, como en v1.1. Nunca hace fallar el índice.
- **Ambigüedad nueva:** que entren más archivos en los niveles intermedios puede convertir en ambigua una referencia que hoy resuelve exacta en todo el repo. `validate` informa esos casos como siempre. El paso 8 mide cuántas hay en el estudio real antes de cerrar; si aparecen, se corrigen en el estudio con el flujo normal de corrección.
- **`neighbourDefs` demasiado grande:** se trunca con `truncated: true`. El subagente sigue pudiendo abrir el vecino.
- **kb con shas inválidos:** `plan`, `archify` y los demás comandos terminan con un error claro, en español y con código distinto de 0, en vez de leer fuera del kb.

## Testing / validation

- pytest, con tests nuevos por paso (1, 2, 3, 4, 6) y el de contenido de la skill (paso 5).
- vitest, si cambia `types.ts`, y e2e de Playwright sin cambios.
- `readcode validate examples/kb fixture` sin problemas.
- Verificación manual sobre `code-kb/fibex-ai-harness` (paso 8), con los conteos de referencias resueltas y ambiguas, antes y después.

## Out of scope

- Volver a explicar el estudio de `fibex-ai-harness`. Las explicaciones actuales siguen siendo válidas; un refresco con los enlaces nuevos sería una corrida aparte de `/readcode update`.
- Resolución de imports con `replace` en `go.mod`, vendoring y workspaces `go.work` con módulos fuera del repo.
- Mejoras equivalentes para otros lenguajes (paquetes de Java, módulos de TS con `paths`).
- Los demás pendientes menores de v1.1 que quedaron diferidos: `--derived-only` más rápido, borrados que no disparan la regeneración, tests faltantes del visor.

## Open questions

- **`_test.go` en el nivel "mismo paquete".** Este plan los incluye solo cuando el archivo actual es un test. La alternativa es incluirlos siempre, lo que da más resoluciones pero puede enlazar código de producción a ayudantes de test.
