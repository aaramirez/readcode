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
        f"{result['skipped']} sin indexar"
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
