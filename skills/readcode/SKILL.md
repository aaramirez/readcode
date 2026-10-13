---
name: readcode
description: Genera y mantiene "estudios" de repositorios de código (explicaciones por bloque, resúmenes de archivo y directorio, overview, diagramas, tours guiados y diffs explicados entre commits) orquestando el CLI determinista `readcode` y subagentes en paralelo; el resultado se navega con `readcode serve`. Úsala cuando pidan "/readcode", "/readcode study|update|diff|tour", "estudia este repo", "genera un estudio de <repo>", "actualiza el estudio", "estudia el último commit", "explica los cambios entre commits", "qué cambió entre <shaA> y <shaB>", "agrega un tour", "haz un recorrido de <flujo>".
---

# readcode

Un **estudio** es un directorio dentro de una base de conocimiento (KB) con una copia del código
por commit y su explicación. El CLI `readcode` hace todo lo determinista (snapshot, símbolos,
plan de trabajo, diff, validación, catálogo) y **nunca llama a un LLM**. Esta skill pone la parte
LLM: reparte el trabajo en subagentes, cada uno escribe archivos JSON/Markdown que cumplen
`schemas/`, y todo pasa por `readcode validate` antes de darse por bueno.

Ejemplo de referencia de calidad: el estudio `fixture` de `examples/kb/` en el repo de readcode.

## Subcomandos

| Invocación | Qué hace |
|---|---|
| `/readcode study <repo> [--sha <rev>] [--kb <dir>] [--name <estudio>]` | Estudio nuevo (o continúa uno a medias) de la revisión `<rev>` (por defecto `HEAD`). |
| `/readcode update <estudio> [--sha <rev>] [--kb <dir>]` | Nuevo snapshot; hereda lo que no cambió y reexplica lo cambiado. |
| `/readcode diff <estudio> <shaA> <shaB> [--kb <dir>]` | Explica el cambio entre dos commits: global + por archivo y hunk. |
| `/readcode tour <estudio> "<pregunta o flujo>" [--sha <rev>] [--kb <dir>]` | Agrega un recorrido guiado a un snapshot ya explicado. |

Sin subcomando: si el usuario da una ruta de repo, es `study`; si nombra un estudio existente,
pregunta qué quiere (update, diff o tour).

## 0. Preparación (todos los subcomandos)

1. **CLI disponible:** ejecuta `readcode --help`. Si falla, detente y pide instalarlo
   (`pip install -e core` desde el repo de readcode). No sigas sin él.
2. **KB:** usa `--kb <dir>` si viene; si no, la variable de entorno `READCODE_KB`; si tampoco,
   pregunta **una sola vez** al usuario. Usa rutas absolutas.
3. **Estudio:** en `study`, el nombre es `--name` o el nombre del directorio del repo en
   kebab-case (minúsculas, dígitos, `.`, `_`, `-`; empieza por letra o dígito; p. ej.
   `Mi Repo_API` → `mi-repo-api`). En los demás subcomandos el estudio debe existir en
   `<KB>/<estudio>/study.json`.
4. **Herramientas opcionales** (si faltan, el estudio se genera igual y se anota en
   `study.json` → `tools`):
   - Graphify: lo detecta `readcode graph` (pone `tools.graphify` solo).
   - Archify: busca `~/.agents/skills/archify/bin/archify.mjs` (o `~/.claude/skills/archify/bin/archify.mjs`)
     y comprueba `node <archify.mjs> doctor`. Anótalo con
     `readcode mark <KB> <STUDY> --archify true` (o `--archify false`). Sin Archify los
     diagramas van como Mermaid (`diagrams/<nombre>.mmd` y bloques ```` ```mermaid ````) y no se
     usan marcadores `[[archify:…]]`.
5. Variables que usa el resto de esta guía:
   - `SKILL_DIR`: el directorio de este `SKILL.md` (las plantillas están en `SKILL_DIR/prompts/`).
   - `KB`, `STUDY`, `SDIR = <KB>/<STUDY>`.
   - `SHA`: el sha **completo** (40 hex) del snapshot, tal como lo imprime `readcode snapshot`
     o como figura en `study.json`.
   - `SNAP = <SDIR>/snapshots/<SHA>`.
   - `LANG`: `study.json` → `language` (por defecto `es`). **Todas** las explicaciones se
     escriben en ese idioma.

## Reglas (siempre)

- **Nunca escribas fuera de `<SDIR>`** (excepto el directorio temporal de trabajo de Archify,
  ver Fase 4, y `<KB>/catalog.json`, que escribe `readcode catalog`). Nunca modifiques el repo
  estudiado.
- **Nunca hagas commit ni push en la KB.** Al final solo **sugieres** el commit.
- Lee el código del snapshot desde los blobs (`readcode context` da la ruta exacta), no del
  working copy: el working copy puede estar en otro commit y los números de línea no casarían.
- Toda afirmación debe salir de código leído de verdad. Si algo no se puede saber desde el repo
  (un servicio externo, una configuración ausente), se dice así.
- Prefiere marcadores `[[ref:…]]` a rutas en prosa (el visor los convierte en enlaces).
- Lo pendiente lo decide `readcode plan`, nunca la memoria de la conversación: re-ejecutar la
  skill continúa donde se quedó.
- Escribe los JSON con UTF-8, indentación 2 y `"schemaVersion": 1`; las rutas siempre con `/` y
  relativas a la raíz del repo.
- No edites `study.json` a mano: el estado del snapshot y `tools.archify` se fijan con
  `readcode mark`.

## Cómo se despacha un subagente

Todos los subagentes se lanzan con la herramienta **Agent** (`subagent_type: "general-purpose"`).
Para paralelizar, pon **varias llamadas Agent en un mismo mensaje** (máximo ~8 a la vez); espera
a que termine la ola y lanza la siguiente. Modelos:

- Explicación de archivos, directorios, refrescos y diff por archivo: modelo intermedio
  (`model: "sonnet"`).
- Overview, diagramas, tours y explicación global del diff: el modelo por defecto (sin `model`).

El mensaje de cada subagente es corto y siempre tiene esta forma (rellena los valores; la
plantilla dice al subagente qué hacer con cada uno):

```
Eres un subagente de readcode. Lee y sigue al pie de la letra <SKILL_DIR>/prompts/<plantilla>.md.
KB: <KB>
Estudio: <STUDY>   (directorio <SDIR>)
SHA: <SHA>         (snapshot <SNAP>)
Idioma: <LANG>
Tarea: <lo específico: lote de archivos, directorios, tour, problemas a corregir…>
Escribe solo los archivos indicados en la plantilla. No ejecutes `readcode validate` (reescribe
links.json e issues.json; lo ejecuta el orquestador). Al terminar responde únicamente con la
lista de archivos escritos y, si algo no pudiste hacer, por qué.
```

No pegues código ni JSON en el mensaje: el subagente lee lo que necesita. En las plantillas,
`{{LANGUAGE}}` es el `Idioma` del mensaje.

Comandos auxiliares (solo lectura):

- `readcode context <KB> <STUDY> --sha <SHA> <path>... --json`: por archivo, el blob exacto del
  snapshot, defs, imports, quién lo importa o usa, vecinos en el grafo y si ya está explicado.
  Lo usan los subagentes.
- `readcode stale <KB> <STUDY> <shaA> <shaB> --json`: documentos heredados que pueden haber
  quedado viejos tras un `update` (ver abajo).

## `/readcode study`

### Fase 1 — Mecánica

```bash
readcode init <KB> <STUDY> --repo <repo> [--title "<Título>"] [--language <idioma>]
readcode snapshot <KB> <STUDY> --sha <rev>
readcode index <KB> <STUDY> --sha <SHA>
readcode graph <KB> <STUDY> --sha <SHA>
readcode plan <KB> <STUDY> --sha <SHA> --json
```

- Si `<SDIR>/study.json` ya existe, **no** hagas `init` (ni `--force`): es un estudio a medias o
  un snapshot más; sigue con `snapshot`.
- `--repo` acepta ruta local o URL. Si es URL, `snapshot` necesita un checkout local: pide al
  usuario la ruta (o, con su permiso, clónalo en un directorio temporal) y añade
  `--repo-path <checkout>` a `readcode snapshot`.
- `readcode snapshot` imprime `Snapshot <sha> (<mensaje>)`: ese es el `SHA` completo.
- `readcode graph` sin Graphify solo avisa; sigue adelante.
- `readcode plan` escribe `<SNAP>/plan.json`:
  `{sha, reusedFrom, reused, reusedDirs, batches: [{id, files: [{path, lines, language}]}],
  dirs: [...], overview, tours, abandoned: [...], done}`. Es la cola de trabajo y la **fuente de
  verdad** de lo pendiente. `reusedFrom` es el snapshot del que hereda (o `null`); `abandoned`
  son archivos sin explicar que el generador abandonó (ver Fase 2), que no cuentan como
  pendientes.

### Fase 2 — Archivos (en paralelo)

1. Lee `<SNAP>/plan.json`. Si `batches` está vacío, pasa a la Fase 3.
2. Lanza **un subagente por lote**, hasta 8 por mensaje, con la plantilla `explain-file.md`,
   `model: "sonnet"` y en `Tarea` la lista de archivos del lote
   (`- <path> (<language>, <lines> líneas)`). Cada uno escribe `<SNAP>/explain/<path>.json`
   según `explain.schema.json`.
3. Al terminar cada ola, vuelve a ejecutar `readcode plan <KB> <STUDY> --sha <SHA> --json` y
   relee `plan.json`: los archivos que fallaron vuelven a aparecer en `batches`, renumerados, y
   reciben un **segundo intento** en la ola siguiente. Repite hasta que `batches` quede vacío.
4. Si un archivo sigue pendiente tras su **segundo intento fallido**, abandónalo registrándolo en
   `<SNAP>/issues.json`:
   `{"file": "explain/<path>.json", "problem": "…", "hint": "…", "source": "generator"}`
   (crea el archivo como `{"schemaVersion": 1, "issues": []}` si no existe; `validate`
   conserva las entradas que no son suyas). Desde entonces `readcode plan` lo lista en
   `abandoned` y no en `batches`, también en corridas futuras: el registro de intentos vive en
   `issues.json`, no en la conversación. Para reintentarlo, el usuario borra esa entrada.

### Fase 3 — Directorios (de abajo hacia arriba)

1. `plan.json` → `dirs` ya viene ordenado del más profundo a la raíz (`""` = raíz, se guarda
   en `dirs/_root.json`).
2. **Repo pequeño** (≤ 8 directorios pendientes en total): **un solo** subagente con la lista
   completa en el orden de `dirs` (él los resume de abajo hacia arriba). Salta los puntos 3–4.
3. Si no, agrupa por profundidad: todos los directorios de la misma profundidad forman una ola;
   dentro de la ola reparte los directorios en subagentes de hasta ~6, juntando **directorios
   hermanos** (mismo padre) en el mismo subagente; directorios no hermanos pueden compartir
   subagente para completar los ~6. Plantilla `dir.md`, `model: "sonnet"`, `Tarea`: la lista de
   directorios.
4. No lances una ola hasta que la anterior (más profunda) haya terminado: cada resumen se
   construye con los de sus hijos.
5. Al final, `readcode plan <KB> <STUDY> --sha <SHA> --json` debe dejar `dirs` vacío; si no,
   repite solo los que falten; tras el segundo intento fallido regístralo en `issues.json`
   (`"file": "dirs/<ruta>.json"`, `source: "generator"`) y sigue (el snapshot quedará `partial`).

### Fase 4 — Diagramas y overview

Solo si `plan.json` → `overview` es `true` (si el overview se heredó, salta a la Fase 5).

1. **Diagramas** (con Archify disponible; como máximo **2 por snapshot**, cada HTML pesa
   ~765 KB):
   - Siempre `arquitectura` (tipo `architecture`).
   - Un segundo (`flujo-datos` de tipo `dataflow`, o `secuencia` de tipo `sequence`) solo si
     aporta algo que la arquitectura no muestra (un pipeline de datos, un request típico).
   - Un subagente por diagrama, en paralelo, plantilla `overview.md` (sección *Diagrama
     Archify*), `Tarea`: `diagrama <nombre> de tipo <tipo>` y la ruta de `archify.mjs`.
     El subagente trabaja en un directorio temporal fuera de la KB y copia solo
     `<nombre>.html` y su fuente `<nombre>.json` a `<SNAP>/diagrams/`.
   - Si `diagrams/` ya tiene diagramas heredados y la estructura de directorios no cambió,
     consérvalos.
   - Sin Archify: el subagente del overview escribe `diagrams/arquitectura.mmd` (Mermaid) en su
     lugar.
2. **Overview:** un subagente, plantilla `overview.md` (sección *Overview*), sin `model`,
   `Tarea`: `overview` y los nombres de los diagramas que existen en `<SNAP>/diagrams/`.
   Escribe `<SNAP>/overview.md`.

### Fase 5 — Tours

Solo si `plan.json` → `tours` es `true` (si se heredaron tours, salta).

1. Con `overview.md`, los resúmenes de directorio y `symbols.json`/`graph/graph.json`, propone
   **3–6 flujos principales**: puntos de entrada (main, CLI, servidor), un request típico de
   punta a punta, jobs/workers, el ciclo de vida de la entidad central. Para cada uno elige un
   `id` en kebab-case, un título y el punto de partida.
2. Un subagente por tour, en paralelo, plantilla `tour.md`, sin `model`, `Tarea`:
   `id`, título, objetivo y punto de partida. Escribe `<SNAP>/tours/<id>.json`.

### Fase 6 — Validación

```bash
readcode validate <KB> <STUDY> --sha <SHA> --json
```

1. Sale con código 1 si hay problemas: es lo esperado mientras haya errores. La salida es una
   lista `[{file, problem, hint}]` con `file` relativo a `<SDIR>`
   (p. ej. `snapshots/<SHA>/explain/app/x.py.json`).
2. Agrupa los problemas por documento y **reenvía cada documento a su autor**: misma plantilla
   que lo generó (`explain/` → `explain-file.md`, `dirs/` → `dir.md`, `tours/` → `tour.md`,
   `overview.md` → `overview.md`, `diffs/` → `diff.md`), en paralelo (máx. 8), con `Tarea`:
   `corrige <ruta del documento>` y los problemas de ese documento copiados tal cual (problema +
   pista). El subagente corrige el archivo existente; no lo reescribe desde cero.
3. Vuelve a validar. Máximo **2 reintentos por documento**; lo que quede se queda en
   `<SNAP>/issues.json` (lo escribe `validate`) y el visor lo muestra como aviso.
4. Después valida también los diffs del estudio (sin `--sha` valida todo, diffs incluidos):

   ```bash
   readcode validate <KB> <STUDY> --json
   ```

   Corrige igual (plantilla `diff.md`) los problemas cuyo `file` empieza por `diffs/`.

### Fase 7 — Cierre

1. `readcode plan <KB> <STUDY> --sha <SHA> --json`. Si `done` es `true`, `abandoned` está vacío
   y `<SNAP>/issues.json` no tiene problemas, el estado es `explained`; si no, `partial`:
   `readcode mark <KB> <STUDY> --sha <SHA> --status explained` (o `--status partial`).
2. `readcode catalog <KB>`.
3. Informa: archivos explicados/heredados, directorios, diagramas, tours, problemas restantes
   (con su archivo), y cómo verlo: `readcode serve <KB>`.
4. **Sugiere** (no ejecutes) el commit en la KB, por ejemplo:
   `git -C <KB> add <STUDY> catalog.json && git -C <KB> commit -m "readcode: <STUDY> @ <sha7>"`.

## `/readcode update <estudio> [--sha <rev>]`

1. Mecánica del nuevo commit (por defecto `HEAD`; añade `--repo-path` si el estudio no tiene
   `repo.localPath`):

   ```bash
   readcode snapshot <KB> <STUDY> --sha <rev>
   readcode index <KB> <STUDY> --sha <SHA>
   readcode graph <KB> <STUDY> --sha <SHA>
   readcode plan <KB> <STUDY> --sha <SHA> --json
   ```

   Si en `study.json` ese snapshot ya está `explained`, no hay nada que actualizar: dilo y
   termina. `plan` hereda por hash de blob las explicaciones de archivos sin cambio, los
   resúmenes de directorios cuyo subárbol es idéntico, tours, diagramas (y el overview si el
   árbol entero es idéntico); `plan.json` lista solo lo que falta.
2. `PREV` = `plan.json` → `reusedFrom` (el snapshot del que `plan` heredó; usa siempre este,
   no lo deduzcas de `study.json`). Si es `null`, no hay nada que heredar: esto es un `study`,
   sigue ese flujo desde la Fase 2. Si no:

   ```bash
   readcode diff <KB> <STUDY> <PREV> <SHA>
   ```

3. **Explicaciones heredadas que pueden haber quedado viejas:**

   ```bash
   readcode stale <KB> <STUDY> <PREV> <SHA> --json
   ```

   Devuelve `changedSymbols` (definiciones que cambiaron) y los documentos heredados que las
   usan: `explain` (archivos sin cambios cuyo código referencia esos símbolos —refs de
   `symbols.json`— o cuyos marcadores apuntan a ellos), `dirs`, `tours` (con los pasos cuyo
   archivo cambió) y `overview`. Para cada `explain` listado lanza subagentes de refresco
   (plantilla `explain-file.md`, *modo refresco*, `model: "sonnet"`, hasta ~10 archivos por
   subagente, en paralelo) con `Tarea`: `refresca`, los archivos y, por cada uno, los símbolos y
   marcadores afectados y el `changedSymbols` completo. Corrigen **solo** las frases que el
   cambio volvió inexactas y **conservan `blobHash`**. Los `dirs` listados que no estén en
   `plan.json` → `dirs` se refrescan igual con `dir.md` (modo refresco); los `tours` listados,
   con `tour.md` (modo refresco). Los marcadores que da `stale` son `ruta#símbolo`, `#símbolo`
   o solo `ruta` (marcadores de líneas `[[ref:ruta:L…]]` hacia un archivo cambiado): cópialos
   tal cual en la `Tarea`. Cuándo lanzarlos: los refrescos de `explain` van en la **misma ola**
   que la Fase 2 (no dependen de ella); los de `dirs` y `tours`, **después** de la Fase 2
   (leen las explicaciones nuevas), junto con la Fase 3. Si `overview` sale listado pero
   `plan.json` → `overview` es `true`, no lo refresques: se regenera en la Fase 4.
4. Fases 2–7 del `study` con este `SHA`. Particularidades:
   - Fase 4: el overview se regenera si `plan.json` → `overview` es `true`. Regenera
     `arquitectura` solo si `changes.json` tiene archivos `added`/`deleted`/`renamed` que cambian
     la estructura (directorios o componentes nuevos o borrados; mira `diagrams/arquitectura.json`:
     si sus componentes son archivos, un archivo de código nuevo o borrado cuenta); si no,
     conserva el heredado. El subagente sobrescribe los dos archivos heredados.
   - Fase 5: no propongas tours nuevos si se heredaron; solo los refrescos del punto 3.
5. Al final ofrece explicar el cambio con `/readcode diff <STUDY> <PREV> <SHA>` (ya existe
   `changes.json`).

## `/readcode diff <estudio> <shaA> <shaB>`

1. Ambos commits deben ser snapshots del estudio (prefijo de sha válido). Si alguno no lo es,
   créalo: `readcode snapshot <KB> <STUDY> --sha <rev>` y `readcode index <KB> <STUDY> --sha <SHA>`
   (no hace falta explicarlo entero; queda `indexed`).
2. `readcode diff <KB> <STUDY> <shaA> <shaB>` → `DDIR = <SDIR>/diffs/<A>..<B>/changes.json`
   (shas completos en el nombre). Cada archivo trae `status` (`added|modified|deleted|renamed`),
   `fromBlob`/`toBlob` y `hunks[{fromRange, toRange, header}]`.
3. Mensajes de commit del rango (si hay checkout local, `repo.localPath`):
   `git -C <localPath> log --format="%h %s%n%b" <A>..<B>`. Guárdalos para los subagentes
   (cópialos en la `Tarea`, no en archivos).
4. **Por archivo** (reanudable: salta los que ya tienen `DDIR/explain/<path>.json`): subagentes
   en paralelo (máx. 8), plantilla `diff.md` (*modo archivo*), `model: "sonnet"`, hasta ~6
   archivos o ~600 líneas cambiadas por subagente; `Tarea`: `modo archivo`, `A`, `B`, `DDIR`,
   los archivos (con su `status`) y los mensajes de commit. En los mensajes de diff (este punto y
   el siguiente) la línea `SHA:` del mensaje tipo lleva `B` (snapshot `<SDIR>/snapshots/<B>`).
5. **Global** (si `DDIR/explain.md` ya existe de una corrida anterior, sáltalo): cuando terminen
   los de archivo, un subagente (plantilla `diff.md`, *modo global*, sin `model`)
   escribe `DDIR/explain.md` a partir de los mensajes de commit, `changes.json` y las
   explicaciones por archivo.
6. `readcode validate <KB> <STUDY> --json`; corrige los problemas de `diffs/<A>..<B>/` como en la
   Fase 6 (máx. 2 reintentos por documento).
7. `readcode catalog <KB>`; resume el cambio en 3–5 líneas al usuario y sugiere el commit en la
   KB.

## `/readcode tour <estudio> "<pregunta o flujo>"`

1. `SHA` = `--sha` si viene; si no, el snapshot más reciente con `status` `explained` (o
   `partial`). Si el snapshot no tiene explicaciones, sugiere antes `/readcode study`.
2. Elige un `id` en kebab-case a partir de la pregunta que no exista en `<SNAP>/tours/`.
3. Un subagente, plantilla `tour.md`, sin `model`, `Tarea`: `id`, la pregunta tal cual y, si lo
   ves claro, el punto de partida (busca en `symbols.json` y en el overview).
4. `readcode validate <KB> <STUDY> --sha <SHA> --json`; corrige solo los problemas de
   `tours/<id>.json` (máx. 2 reintentos).
5. Resume el tour (título y pasos) y sugiere el commit en la KB.

## Si algo sale mal

- Un comando `readcode` que falla con `error: …` es un error de uso o de datos: léelo, corrige
  la causa (ruta, sha, falta un paso previo) y repite. No edites a mano `tree.json`,
  `symbols.json`, `plan.json`, `changes.json`, `links.json` ni `issues.json` (salvo añadir
  entradas `source: "generator"` en `issues.json`).
- Si se interrumpe, vuelve a invocar el mismo subcomando: `readcode plan` (o la existencia de
  los archivos en el caso de `diff`) dice qué falta.
