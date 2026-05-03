"""`dojo runs` — list and inspect agent runs."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from dojo.agents.types import AgentRun
from dojo.cli._lab import build_cli_lab
from dojo.cli.state import CLIStateError, resolve_domain

console = Console()
app = typer.Typer(help="List and inspect agent runs")


@app.command("ls")
def ls(
    domain: str | None = typer.Option(
        None, "--domain", "-d", help="Domain id or name (defaults to current)"
    ),
    all_domains: bool = typer.Option(False, "--all", help="Show runs across all domains"),
    json_output: bool = typer.Option(False, "--json", help="Emit raw JSON"),
    limit: int = typer.Option(20, "--limit", help="Max runs to show"),
) -> None:
    """List recent runs (defaults to the current domain)."""

    async def _run() -> None:
        lab, settings = build_cli_lab()
        base_dir = Path(settings.storage.base_dir)
        domain_id: str | None = None

        if not all_domains:
            try:
                d = await resolve_domain(lab, base_dir=base_dir, override=domain)
            except CLIStateError as e:
                console.print(f"[red]error:[/red] {e}")
                raise typer.Exit(code=1) from e
            domain_id = d.id

        runs = await lab.run_store.list(domain_id=domain_id)
        runs.sort(key=lambda r: r.started_at or r.id, reverse=True)
        runs = runs[:limit]

        if json_output:
            console.print_json(data=[_run_to_dict(r) for r in runs])
            return

        if not runs:
            console.print("[dim]no runs found[/dim]")
            return

        table = Table(show_header=True, header_style="bold")
        table.add_column("id", style="cyan")
        table.add_column("status")
        table.add_column("domain")
        table.add_column("started")
        table.add_column("turns", justify="right")
        table.add_column("cost", justify="right")
        for r in runs:
            cost = r.result.total_cost_usd if r.result and r.result.total_cost_usd else None
            cost_str = f"${cost:.4f}" if cost is not None else "-"
            turns = r.result.num_turns if r.result else 0
            started = r.started_at.isoformat(timespec="seconds") if r.started_at else "-"
            table.add_row(
                r.id, r.status.value, r.domain_id[:12] + "…", started, str(turns), cost_str
            )
        console.print(table)

    asyncio.run(_run())


@app.command("show")
def show(
    run_id: str | None = typer.Argument(None, help="Run id (defaults to the current run)"),
    json_output: bool = typer.Option(False, "--json", help="Emit raw JSON"),
    events: bool = typer.Option(False, "--events", help="Print every event"),
) -> None:
    """Show a run's status, metrics, and (optionally) events."""

    async def _run() -> None:
        lab, settings = build_cli_lab()
        base_dir = Path(settings.storage.base_dir)

        target_id = run_id
        if target_id is None:
            from dojo.cli.state import load_state

            target_id = load_state(base_dir).current_run_id
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

        if json_output:
            console.print_json(data=_run_to_dict(r, include_events=events))
            return

        # Friendly summary
        console.print(f"[bold]run[/bold] {r.id}")
        console.print(f"  status: {r.status.value}")
        console.print(f"  domain: {r.domain_id}")
        if r.started_at:
            console.print(f"  started: {r.started_at.isoformat(timespec='seconds')}")
        if r.completed_at:
            console.print(f"  completed: {r.completed_at.isoformat(timespec='seconds')}")
        if r.result:
            console.print(f"  turns: {r.result.num_turns}")
            if r.result.total_cost_usd is not None:
                console.print(f"  cost: ${r.result.total_cost_usd:.4f}")
        if r.error:
            console.print(f"  [red]error:[/red] {r.error}")
        console.print(f"  events: {len(r.events)}")

        if events:
            console.print("\n[bold]events[/bold]")
            for e in r.events:
                console.print(
                    f"  [{e.timestamp.isoformat(timespec='seconds')}] "
                    f"[dim]{e.event_type}[/dim] "
                    f"{json.dumps(e.data, default=str)[:200]}"
                )

    asyncio.run(_run())


def _run_to_dict(r: AgentRun, *, include_events: bool = False) -> dict:
    out = {
        "id": r.id,
        "domain_id": r.domain_id,
        "status": r.status.value,
        "started_at": r.started_at.isoformat() if r.started_at else None,
        "completed_at": r.completed_at.isoformat() if r.completed_at else None,
        "num_turns": r.result.num_turns if r.result else 0,
        "total_cost_usd": r.result.total_cost_usd if r.result else None,
        "error": r.error,
        "event_count": len(r.events),
    }
    if include_events:
        out["events"] = [
            {
                "id": e.id,
                "timestamp": e.timestamp.isoformat(),
                "event_type": e.event_type,
                "data": e.data,
            }
            for e in r.events
        ]
    return out
