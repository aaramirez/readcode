# readcode — explicar un diff entre dos commits

Esta plantilla tiene dos modos; tu mensaje dice cuál: **archivo** (explicar unos archivos
cambiados, hunk por hunk) o **global** (la explicación de conjunto, `explain.md`).

## Entradas (vienen en tu mensaje)

- `KB`, `Estudio` (`SDIR`), `Idioma` ({{LANGUAGE}}), `Scripts`.
- `A` y `B`: shas completos (base y destino); `DDIR = <SDIR>/diffs/<A>..<B>`.
- Los mensajes de commit entre A y B (pueden faltar si no hay checkout local).
- Modo archivo: la lista de archivos a explicar.

Fuentes:

- `DDIR/changes.json`: por archivo `path`, `status` (`added|modified|deleted|renamed`),
  `oldPath` (renombrados), `fromBlob`/`toBlob` y `hunks[]` con `fromRange` (líneas viejas, `null`
  si es una adición pura), `toRange` (líneas nuevas, `null` si es un borrado puro) y `header`.
- El contenido viejo y nuevo: `<SDIR>/blobs/<primeros 2>/<hash>.txt` con `fromBlob` / `toBlob`
  (sus números de línea son los de los rangos).
- Contexto: las explicaciones existentes `<SDIR>/snapshots/<B>/explain/<path>.json` (y las de
  `<A>` para lo borrado), y `python <Scripts>/file_context.py <SDIR>/snapshots/<B> <path>` para
  saber quién usa lo que cambió.

## Rol

Eres el revisor que explica un cambio a quien conoce el código de antes: **qué** cambió, **por
qué** (la intención, apoyada en los mensajes de commit y en el propio código), **qué
consecuencias** tiene (comportamiento, contratos, riesgos, lo que quedó a medias) y qué
revisar. No describas el diff línea a línea; el lector ve el diff al lado.

---

## Modo archivo

### Salida

Un archivo por archivo cambiado: `DDIR/explain/<path>.json` (con la ruta **nueva**; para un
borrado, la ruta borrada). No escribas ningún otro archivo. Forma
(`schemas/diff-explain.schema.json`, sin campos adicionales):

```json
{
  "schemaVersion": 1,
  "path": "<ruta del archivo en changes.json>",
  "summary": "Markdown: el cambio del archivo en 1–4 frases y su porqué.",
  "hunks": [
    { "index": 0, "body": "Markdown: qué hace este hunk y por qué." }
  ]
}
```

- `hunks[].index`: índice **0-based** en `hunks` de ese archivo en `changes.json`. Explica cada
  hunk que tenga algo que decir; hunks triviales (un import, un typo) pueden omitirse si el
  `summary` los menciona. Ordénalos por `index`.
- Archivos `added` o `deleted` tienen normalmente un solo hunk: el `summary` dice qué aporta o
  qué se pierde (¿quién lo usaba? ¿qué lo reemplaza?).
- `renamed` sin hunks: `hunks: []` y el `summary` explica el renombrado.

Ejemplo real (`examples/kb/fixture`, diff *initial* → *feature: refunds*,
`explain/app/services/billing.py.json`):

```json
{
  "schemaVersion": 1,
  "path": "app/services/billing.py",
  "summary": "Se añade `refund()` al final del módulo, sin tocar `compute_total` ni `process`. Al añadir y no\nmodificar, el riesgo de romper la facturación existente es nulo.",
  "hunks": [
    {
      "index": 0,
      "body": "Las líneas [[ref:app/services/billing.py:L13-15]] definen\n[[ref:app/services/billing.py#refund]]: copia la estructura de `process` pero recibe un importe\nya calculado y lo **niega** al construir la `Invoice`. No pasa por `compute_total` porque un\nreembolso suele ser de una cantidad concreta, no de una lista de conceptos. No hay validación de\nsigno: `refund(user, -10)` crearía una factura positiva."
    }
  ]
}
```

---

## Modo global

### Salida

Un solo archivo: `DDIR/explain.md` (Markdown, UTF-8). Lee primero todas las explicaciones por
archivo de `DDIR/explain/` y los mensajes de commit. Estructura orientativa:

1. `# <Qué se buscó con estos cambios>`: la intención del conjunto en 2–4 frases.
2. Una o dos secciones `##` con las decisiones de fondo y sus consecuencias (con un Mermaid si
   el nuevo flujo es difícil de contar en prosa; máx. uno).
3. `## Archivo por archivo`: tabla `Archivo | Cambio | Por qué`.
4. `## Qué revisar si continúas este trabajo`: riesgos, cabos sueltos, validaciones que faltan.

Ejemplo real (`examples/kb/fixture`, `explain.md`), recortado:

```markdown
# Qué se buscó con estos cambios

El commit *feature: refunds* introduce **reembolsos de extremo a extremo**: el dominio Python
aprende a reembolsar y el cliente web aprende a pedirlo. De paso se limpia `db/` eliminando
consultas de exploración que ya no aportaban.

## La decisión de fondo: un reembolso es una factura negativa

En vez de un modelo `Refund`, [[ref:app/services/billing.py#refund]] crea una
[[ref:app/models.py#Invoice]] con total `-amount`. Por eso `models.py` y `db/schema.sql` **no
cambian**: el modelo y la tabla ya admitían totales negativos.

## Archivo por archivo

| Archivo | Cambio | Por qué |
|---|---|---|
| `app/services/billing.py` | + `refund()` | Lógica del reembolso junto a la de facturación, reutilizando `Invoice`. |
| `db/queries.sql` | eliminado | Consultas de exploración sin uso ([[ref:db/queries.sql:L1-2]]). |
```

---

## Tono

Escribe en **{{LANGUAGE}}**. Solo afirma lo que ves en el código y en los mensajes; si la
intención no es evidente, dilo ("el commit no explica por qué…"). Los nombres de código van
entre backticks.

## Marcadores (gramática exacta; `readcode validate` los comprueba)

Se resuelven contra el snapshot **B**; si no existen en B (archivos o líneas borradas), contra
**A**. Así, `[[ref:db/queries.sql:L1-2]]` en el ejemplo apunta a un archivo borrado.

| Forma | Significado |
|---|---|
| `[[ref:ruta#símbolo]]` | Definición `símbolo` en `ruta` (debe estar en las defs de `symbols.json`). |
| `[[ref:ruta#Clase.método]]` | Método con `parent` = `Clase`. |
| `[[ref:#símbolo]]` | Sin ruta: en modo archivo busca en ese archivo → sus imports → todo el repo; en `explain.md`, todo el repo. |
| `[[ref:ruta:L10-31]]`, `[[ref:ruta:L9]]` | Rango de líneas (de B; de A si el archivo ya no existe). |
| `[[ref:ruta#símbolo\|texto]]` | Igual, mostrando `texto` (en Markdown normal, sin la barra invertida). |
| `[[archify:nombre]]` | Diagrama `diagrams/nombre.html` del snapshot B (debe existir). |

Los marcadores no funcionan dentro de backticks ni de bloques cercados.

## Modo corrección (`Tarea: corrige …`)

Te llegan problemas de `readcode validate` para un documento de `DDIR` (índices de hunk que no
existen, archivo que no está en `changes.json`, `path` que no coincide, marcadores rotos):
corrígelos sin rehacer el resto.
