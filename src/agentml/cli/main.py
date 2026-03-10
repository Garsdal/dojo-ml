"""AgentML CLI — main entry point."""

import typer

from agentml._version import __version__

app = typer.Typer(
    name="agentml",
    help="AgentML — AI-powered experiment orchestration",
    no_args_is_help=True,
)


def version_callback(value: bool) -> None:
    if value:
        typer.echo(f"AgentML v{__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False,
        "--version",
        "-v",
        help="Show version and exit.",
        callback=version_callback,
        is_eager=True,
    ),
) -> None:
    """AgentML CLI."""


@app.command()
def start(
    host: str = typer.Option("127.0.0.1", help="Host to bind to"),
    port: int = typer.Option(8000, help="Port to listen on"),
    no_frontend: bool = typer.Option(
        False, "--no-frontend", help="Skip launching the frontend dev server"
    ),
) -> None:
    """Start the AgentML server."""
    from agentml.cli.start import start as _start

    _start(host=host, port=port, no_frontend=no_frontend)


@app.command()
def run(
    prompt: str = typer.Argument(help="The task prompt to run"),
    host: str = typer.Option("127.0.0.1", help="Server host"),
    port: int = typer.Option(8000, help="Server port"),
) -> None:
    """Submit a task to a running AgentML server."""
    from agentml.cli.run import run as _run

    _run(prompt=prompt, host=host, port=port)


# Register config subcommand group
from agentml.cli.config import config_app  # noqa: E402

app.add_typer(config_app, name="config")
