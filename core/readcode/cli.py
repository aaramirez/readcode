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
