"""`dojo stop` — mark a run STOPPED on disk.

This only updates the persisted record. It does NOT halt an in-process
``dojo run`` from another terminal — for that, send Ctrl-C in the terminal
that started the run. ``dojo stop`` is useful for:

  1. Recovering records left ``RUNNING`` after a hard kill (kill -9, crash).
  2. Stopping server-mode runs (``dojo start``) once the server polls
     ``run_store`` for cooperative shutdown signals.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path

import typer
from rich.console import Console

from dojo.agents.types import RunStatus
from dojo.cli._lab import build_cli_lab
from dojo.cli.state import load_state

console = Console()


def stop(
    run_id: str | None = typer.Argument(None, help="Run id (defaults to the current run)"),
) -> None:
    """Mark a run as STOPPED on disk.

    For the foreground ``dojo run`` case use Ctrl-C in that terminal — this
    command can't reach an in-process orchestrator from another terminal.
    """

    async def _run() -> None:
        lab, settings = build_cli_lab()
        base_dir = Path(settings.storage.base_dir)

        target_id = run_id or load_state(base_dir).current_run_id
        if target_id is None:
            console.print(
                "[red]error:[/red] no run id given and no current_run_id set. "
                "Pass a run id or run `dojo run` first."
            )
            raise typer.Exit(code=1)

        r = await lab.run_store.load(target_id)
        if r is None:
            console.print(f"[red]error:[/red] run {target_id!r} not found")
            raise typer.Exit(code=1)

        if r.status not in (RunStatus.RUNNING, RunStatus.PENDING):
            console.print(
                f"[yellow]run {r.id} already in terminal state ({r.status.value})[/yellow]"
            )
            return

        r.status = RunStatus.STOPPED
        r.completed_at = datetime.now(UTC)
        await lab.run_store.save(r)
        console.print(f"[yellow]■[/yellow] run {r.id} marked STOPPED on disk")

    asyncio.run(_run())
