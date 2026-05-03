"""`dojo stop` — request a graceful stop for a run.

Drops a stop-signal sentinel that any orchestrator running ``execute()`` for
this run polls (foreground ``dojo run``, server-mode runs). The orchestrator
then asks the backend to interrupt itself, so the SDK has a chance to emit a
final ResultMessage with cost/turn data before exiting.

If no orchestrator picks the signal up within a short window (the run's
process crashed without recording a terminal status), we fall back to marking
the on-disk record STOPPED so it stops appearing as RUNNING in `dojo runs`.
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

# How long to wait for an active orchestrator to pick the signal up before
# falling back to the on-disk cleanup path. Must comfortably exceed the
# orchestrator's stop-poll interval (currently 1s).
_GRACE_WINDOW_S = 4.0
_POLL_INTERVAL_S = 0.25


def stop(
    run_id: str | None = typer.Argument(None, help="Run id (defaults to the current run)"),
) -> None:
    """Request a graceful stop for a run.

    Sends a stop signal that the orchestrator picks up between events, asking
    the backend to interrupt cleanly. For a forceful stop, send Ctrl-C in the
    terminal that started ``dojo run`` instead — that recovers knowledge atoms
    but loses cost data.
    """

    asyncio.run(_stop_async(run_id))


async def _stop_async(run_id: str | None) -> None:
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
        console.print(f"[yellow]run {r.id} already in terminal state ({r.status.value})[/yellow]")
        return

    await lab.run_store.request_stop(r.id)
    console.print(f"[yellow]■[/yellow] stop signal sent to run {r.id}")

    # Wait for an active orchestrator to honour the signal. If one is running
    # it will save a terminal status within ~1-2 polling cycles.
    waited = 0.0
    while waited < _GRACE_WINDOW_S:
        await asyncio.sleep(_POLL_INTERVAL_S)
        waited += _POLL_INTERVAL_S
        latest = await lab.run_store.load(r.id)
        if latest and latest.status in (
            RunStatus.STOPPED,
            RunStatus.COMPLETED,
            RunStatus.FAILED,
        ):
            console.print(
                f"[green]✓[/green] run {r.id} {latest.status.value} "
                f"(picked up by active orchestrator)"
            )
            return

    # Nobody picked it up — the run's process is gone. Mark STOPPED on disk so
    # `dojo runs` shows it correctly, and clear the now-orphaned signal file.
    latest = await lab.run_store.load(r.id) or r
    latest.status = RunStatus.STOPPED
    latest.completed_at = datetime.now(UTC)
    await lab.run_store.save(latest)
    await lab.run_store.clear_stop_request(latest.id)
    console.print(
        f"[yellow]■[/yellow] no active orchestrator — run {latest.id} marked STOPPED on disk"
    )
