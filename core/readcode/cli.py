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
