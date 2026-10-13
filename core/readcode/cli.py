from pathlib import Path
from typing import Annotated, Optional

import typer

from readcode import __version__

app = typer.Typer(help="readcode: estudios de repositorios de código.", no_args_is_help=True)


@app.callback()
def main() -> None:
    """readcode: estudios de repositorios de código."""


@app.command()
def version() -> None:
    """Muestra la versión."""
    typer.echo(__version__)


@app.command()
def init(
    kb_dir: Annotated[Path, typer.Argument(help="Directorio de la base de conocimiento.")],
    study: Annotated[str, typer.Argument(help="Nombre del estudio.")],
    repo: Annotated[str, typer.Option("--repo", help="Ruta local o URL del repositorio.")],
    title: Annotated[Optional[str], typer.Option(help="Título del estudio.")] = None,
    language: Annotated[str, typer.Option(help="Idioma de las explicaciones.")] = "es",
    force: Annotated[bool, typer.Option("--force", help="Sobrescribe study.json.")] = False,
) -> None:
    """Crea <kb>/<study>/study.json."""
    from readcode.init_cmd import InitError, init_study

    try:
        path = init_study(kb_dir, study, repo, title=title, language=language, force=force)
    except InitError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1)
    typer.echo(f"Creado {path}")


@app.command()
def snapshot(
    kb_dir: Annotated[Path, typer.Argument(help="Directorio de la base de conocimiento.")],
    study: Annotated[str, typer.Argument(help="Nombre del estudio.")],
    sha: Annotated[str, typer.Option("--sha", help="Revisión git (sha, rama, tag).")],
    repo_path: Annotated[Optional[Path], typer.Option("--repo-path", help="Checkout local.")] = None,
) -> None:
    """Toma un snapshot de una revisión: blobs + tree.json."""
    from readcode.snapshot import SnapshotError, snapshot_study

    try:
        entry = snapshot_study(kb_dir, study, sha, repo_path)
    except SnapshotError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1)
    typer.echo(f"Snapshot {entry['sha']} ({entry['message']})")


@app.command()
def index(
    kb_dir: Annotated[Path, typer.Argument(help="Directorio de la base de conocimiento.")],
    study: Annotated[str, typer.Argument(help="Nombre del estudio.")],
    sha: Annotated[str, typer.Option("--sha", help="SHA del snapshot (completo o prefijo único).")],
) -> None:
    """Extrae símbolos (defs, refs, imports) con tree-sitter: symbols.json."""
    from readcode.indexer import IndexingError, index_snapshot

    try:
        result = index_snapshot(kb_dir, study, sha)
    except IndexingError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1)
    typer.echo(
        f"Indexado {result['sha']}: {result['indexed']} archivos con símbolos, "
        f"{result['skipped']} sin indexar ({result['failed']} con errores)"
    )


@app.command()
def plan(
    kb_dir: Annotated[Path, typer.Argument(help="Directorio de la base de conocimiento.")],
    study: Annotated[str, typer.Argument(help="Nombre del estudio.")],
    sha: Annotated[str, typer.Option("--sha", help="SHA del snapshot (completo o prefijo único).")],
    batch_lines: Annotated[int, typer.Option("--batch-lines", help="Máximo de líneas por lote.")] = 1500,
    as_json: Annotated[bool, typer.Option("--json", help="Salida en JSON.")] = False,
) -> None:
    """Cola de trabajo para la skill: reutiliza explicaciones y lista lo pendiente."""
    import json

    from readcode.plan_cmd import PlanError, plan_snapshot, summarize

    try:
        result = plan_snapshot(kb_dir, study, sha, batch_lines)
    except PlanError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1)
    typer.echo(json.dumps(result, indent=2, ensure_ascii=False) if as_json else summarize(result))


@app.command()
def graph(
    kb_dir: Annotated[Path, typer.Argument(help="Directorio de la base de conocimiento.")],
    study: Annotated[str, typer.Argument(help="Nombre del estudio.")],
    sha: Annotated[str, typer.Option("--sha", help="SHA del snapshot (completo o prefijo único).")],
) -> None:
    """Genera el grafo del snapshot con graphify (opcional)."""
    from readcode.graph_cmd import GraphError, graph_snapshot

    try:
        ok = graph_snapshot(kb_dir, study, sha)
    except GraphError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1)
    if ok:
        typer.echo("Grafo generado")


@app.command()
def diff(
    kb_dir: Annotated[Path, typer.Argument(help="Directorio de la base de conocimiento.")],
    study: Annotated[str, typer.Argument(help="Nombre del estudio.")],
    sha_a: Annotated[str, typer.Argument(help="SHA base (completo o prefijo).")],
    sha_b: Annotated[str, typer.Argument(help="SHA destino (completo o prefijo).")],
) -> None:
    """Calcula changes.json entre dos snapshots estudiados."""
    from readcode.diff_cmd import DiffError, diff_snapshots

    try:
        doc = diff_snapshots(kb_dir, study, sha_a, sha_b)
    except DiffError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1)
    typer.echo(f"Diff {doc['from']}..{doc['to']}: {len(doc['files'])} archivos")


@app.command("validate")
def validate_cmd(
    kb_dir: Annotated[Path, typer.Argument(help="Directorio de la base de conocimiento.")],
    study: Annotated[str, typer.Argument(help="Nombre del estudio.")],
    sha: Annotated[Optional[str], typer.Option("--sha", help="Solo este snapshot (y sus diffs).")] = None,
    as_json: Annotated[bool, typer.Option("--json", help="Salida en JSON.")] = False,
    derived_only: Annotated[bool, typer.Option(
        "--derived-only", help="Solo regenera links.json y search.json; no toca issues.json ni falla por problemas.")] = False,
) -> None:
    """Valida el estudio; escribe links.json e issues.json. Exit 1 si hay problemas (los avisos no cuentan)."""
    import json

    from readcode.validate_cmd import ValidateError, format_problems, is_warning, validate_study

    try:
        problems = validate_study(kb_dir, study, sha, derived_only=derived_only)
    except ValidateError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1)
    if derived_only:
        typer.echo("Derivados regenerados (links.json, search.json)")
        return
    typer.echo(json.dumps(problems, indent=2, ensure_ascii=False) if as_json
               else format_problems(problems))
    if any(not is_warning(p) for p in problems):  # warnings (legacy-root) do not fail
        raise typer.Exit(1)


@app.command()
def migrate(
    kb_dir: Annotated[Path, typer.Argument(help="Directorio de la base de conocimiento.")],
    study: Annotated[Optional[str], typer.Argument(help="Nombre del estudio (todos si se omite).")] = None,
) -> None:
    """Migra un kb de v1 al formato actual (raíz de dirs: dirs/_root.json -> dir-root.json)."""
    from readcode.migrate_cmd import MigrateError, format_migrated, migrate_study

    try:
        moved = migrate_study(kb_dir, study)
    except MigrateError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1)
    typer.echo(format_migrated(moved))


@app.command()
def catalog(
    kb_dir: Annotated[Path, typer.Argument(help="Directorio de la base de conocimiento.")],
) -> None:
    """Regenera <kb>/catalog.json."""
    from readcode.catalog_cmd import CatalogError, build_catalog

    try:
        cat, warnings = build_catalog(kb_dir)
    except CatalogError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1)
    for w in warnings:
        typer.echo(f"aviso: {w}", err=True)
    typer.echo(f"catalog.json: {len(cat['studies'])} estudios")


@app.command()
def serve(
    kb_dir: Annotated[Path, typer.Argument(help="Directorio de la base de conocimiento.")],
    port: Annotated[int, typer.Option("--port", help="Puerto.")] = 8765,
    no_open: Annotated[bool, typer.Option("--no-open", help="No abre el navegador.")] = False,
    no_refresh: Annotated[bool, typer.Option(
        "--no-refresh", help="No regenera los derivados obsoletos al arrancar (kb de solo lectura).")] = False,
) -> None:
    """Sirve el visor en / y el directorio de estudios en /kb/."""
    import webbrowser

    from readcode.server import make_server, refresh_on_startup

    if not kb_dir.is_dir():
        typer.echo(f"error: {kb_dir} no es un directorio", err=True)
        raise typer.Exit(1)
    if not no_refresh:
        refresh_on_startup(kb_dir, echo=lambda m: typer.echo(m, err=True))
    server = make_server(kb_dir, port=port)
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    typer.echo(f"Sirviendo {kb_dir} en {url} (Ctrl+C para salir)")
    if not no_open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


@app.command("install-skill")
def install_skill_cmd(
    dest: Annotated[Optional[Path], typer.Option(
        "--dest", help="Directorio de skills de Claude Code (por defecto ~/.claude/skills).")] = None,
    force: Annotated[bool, typer.Option("--force", help="Sobrescribe una instalación existente.")] = False,
) -> None:
    """Instala la skill /readcode de Claude Code (copia skills/readcode)."""
    from readcode.install_skill import InstallSkillError, install_skill

    try:
        path = install_skill(dest, force=force)
    except (InstallSkillError, OSError) as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1)
    typer.echo(f"Skill instalada en {path}")


@app.command()
def context(
    kb_dir: Annotated[Path, typer.Argument(help="Directorio de la base de conocimiento.")],
    study: Annotated[str, typer.Argument(help="Nombre del estudio.")],
    paths: Annotated[list[str], typer.Argument(help="Rutas de archivo del repo.")],
    sha: Annotated[str, typer.Option("--sha", help="SHA del snapshot (completo o prefijo único).")],
    as_json: Annotated[bool, typer.Option("--json", help="Salida en JSON.")] = False,
) -> None:
    """Contexto de archivos para la skill: blob, defs, imports, usos, vecinos en el grafo."""
    import json

    from readcode.context_cmd import ContextError, file_context, format_context

    try:
        items = file_context(kb_dir, study, sha, paths)
    except ContextError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1)
    typer.echo(json.dumps(items, indent=2, ensure_ascii=False) if as_json else format_context(items))


@app.command()
def stale(
    kb_dir: Annotated[Path, typer.Argument(help="Directorio de la base de conocimiento.")],
    study: Annotated[str, typer.Argument(help="Nombre del estudio.")],
    sha_a: Annotated[str, typer.Argument(help="SHA base (del que se heredó).")],
    sha_b: Annotated[str, typer.Argument(help="SHA nuevo.")],
    as_json: Annotated[bool, typer.Option("--json", help="Salida en JSON.")] = False,
) -> None:
    """Documentos heredados que pueden haber quedado viejos tras un update (requiere diff)."""
    import json

    from readcode.stale_cmd import StaleError, format_stale, stale_docs

    try:
        result = stale_docs(kb_dir, study, sha_a, sha_b)
    except StaleError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1)
    typer.echo(json.dumps(result, indent=2, ensure_ascii=False) if as_json else format_stale(result))


@app.command()
def mark(
    kb_dir: Annotated[Path, typer.Argument(help="Directorio de la base de conocimiento.")],
    study: Annotated[str, typer.Argument(help="Nombre del estudio.")],
    sha: Annotated[Optional[str], typer.Option("--sha", help="Snapshot cuyo estado se fija.")] = None,
    status: Annotated[Optional[str], typer.Option(
        "--status", help="indexed | explained | partial (requiere --sha).")] = None,
    archify: Annotated[Optional[str], typer.Option(
        "--archify", help="true | false: si hay diagramas Archify.")] = None,
) -> None:
    """Fija el estado de un snapshot y/o tools.archify en study.json."""
    from readcode.mark_cmd import MarkError, mark_study

    flag = None
    if archify is not None:
        if archify.lower() not in ("true", "false"):
            typer.echo("error: --archify must be true or false", err=True)
            raise typer.Exit(1)
        flag = archify.lower() == "true"
    try:
        mark_study(kb_dir, study, sha=sha, status=status, archify=flag)
    except MarkError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1)
    typer.echo("study.json actualizado")


@app.command()
def archify(
    kb_dir: Annotated[Path, typer.Argument(help="Directorio de la base de conocimiento.")],
    study: Annotated[str, typer.Argument(help="Nombre del estudio.")],
    sha: Annotated[str, typer.Argument(help="SHA del snapshot (completo o prefijo único).")],
    name: Annotated[str, typer.Argument(help="Nombre del diagrama ([A-Za-z0-9._-]).")],
    diagram_type: Annotated[str, typer.Argument(
        metavar="TYPE", help="Tipo Archify (architecture, dataflow, sequence...).")],
    input_json: Annotated[Path, typer.Argument(help="JSON de entrada para Archify.")],
    repo_root: Annotated[Optional[Path], typer.Option(
        "--repo-root", help="Checkout del repo en el SHA (para la evidencia de Archify).")] = None,
    quality: Annotated[Optional[str], typer.Option(
        "--quality", help="standard | showcase (nivel de calidad de Archify).")] = None,
) -> None:
    """Finaliza un diagrama con Archify: diagrams/<name>.html y .json. Exit 2 si falta node o Archify, o falla."""
    from readcode.archify_cmd import ArchifyError, render_diagram

    try:
        out = render_diagram(kb_dir, study, sha, name, diagram_type, input_json, repo_root, quality)
    except ArchifyError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(2)
    typer.echo(f"Diagrama escrito en {out}")


@app.command()
def grammars(
    langs: Annotated[Optional[list[str]], typer.Argument(help="Gramáticas (todas si se omite).")] = None,
    fetch: Annotated[bool, typer.Option("--fetch", help="Descarga las gramáticas indicadas.")] = False,
) -> None:
    """Lista las gramáticas tree-sitter y si están en caché; --fetch las descarga."""
    from readcode.grammars_cmd import GrammarsError, fetch_grammars, grammar_status

    try:
        if fetch:
            typer.echo(f"Gramáticas disponibles: {', '.join(fetch_grammars(langs or None))}")
            return
        for lang, cached in grammar_status(langs or None):
            typer.echo(f"{lang}\t{'en caché' if cached else 'falta (readcode grammars --fetch)'}")
    except GrammarsError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1)
