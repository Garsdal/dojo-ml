"""`dojo program` — view and edit the current domain's PROGRAM.md."""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import sys
from pathlib import Path

import typer
from rich.console import Console

from dojo.cli._lab import build_cli_lab
from dojo.cli.state import CLIStateError, resolve_domain
from dojo.runtime.program_loader import (
    default_program_template,
    resolve_program_path,
)

console = Console()
app = typer.Typer(help="View and edit the steering prompt (PROGRAM.md)")


def _exit_user(msg: str) -> None:
    console.print(f"[red]error:[/red] {msg}")
    raise typer.Exit(code=1)


@app.command("show")
def show(
    domain: str | None = typer.Option(None, "--domain", "-d", help="Domain id or name"),
) -> None:
    """Print the contents of the current domain's PROGRAM.md."""

    async def _run() -> None:
        lab, settings = build_cli_lab()
        try:
            d = await resolve_domain(lab, base_dir=Path(settings.storage.base_dir), override=domain)
        except CLIStateError as e:
            _exit_user(str(e))
            return

        path = resolve_program_path(d, base_dir=Path(settings.storage.base_dir))
        if not path.exists():
            console.print(f"[yellow]no PROGRAM.md at {path}[/yellow]")
            console.print("Run `dojo program edit` to create one.")
            return
        console.print(f"[dim]{path}[/dim]\n")
        console.print(path.read_text())

    asyncio.run(_run())


@app.command("edit")
def edit(
    domain: str | None = typer.Option(None, "--domain", "-d", help="Domain id or name"),
    editor: str | None = typer.Option(
        None, "--editor", help="Editor command (defaults to $EDITOR or $VISUAL)"
    ),
) -> None:
    """Open the current domain's PROGRAM.md in $EDITOR.

    Creates the file with a templated default if it doesn't exist.
    """

    async def _run() -> Path:
        lab, settings = build_cli_lab()
        try:
            d = await resolve_domain(lab, base_dir=Path(settings.storage.base_dir), override=domain)
        except CLIStateError as e:
            _exit_user(str(e))
            raise  # unreachable

        path = resolve_program_path(d, base_dir=Path(settings.storage.base_dir))
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(default_program_template(d))
            console.print(f"[green]created[/green] {path}")
        return path

    path = asyncio.run(_run())

    cmd = editor or os.environ.get("VISUAL") or os.environ.get("EDITOR")
    if not cmd:
        # Last-resort: print the file path so the user can open it themselves.
        console.print(
            f"[yellow]no editor configured[/yellow] (set $EDITOR or pass --editor). File: {path}"
        )
        return

    binary = shutil.which(cmd.split()[0]) or cmd.split()[0]
    try:
        subprocess.run([binary, str(path)], check=False)
    except FileNotFoundError:
        console.print(f"[red]editor not found:[/red] {binary}", style="red")
        sys.exit(1)
