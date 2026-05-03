"""`dojo run` — start an agent run on the current domain (in-process, no server)."""

from __future__ import annotations

import asyncio
import contextlib
from pathlib import Path

import typer
from rich.console import Console

from dojo.agents.factory import create_agent_backend
from dojo.agents.orchestrator import AgentOrchestrator
from dojo.agents.types import AgentEvent, RunStatus
from dojo.cli._lab import build_cli_lab
from dojo.cli.state import CLIStateError, resolve_domain, set_current_run_id
from dojo.runtime.program_loader import load_program

console = Console()


# Exit codes per NEXT_STEPS.md CLI conventions
EXIT_USER_ERROR = 1
EXIT_SYSTEM_ERROR = 2
EXIT_TASK_NOT_READY = 3


def run(
    domain: str | None = typer.Option(None, "--domain", "-d", help="Domain id or name"),
    max_turns: int = typer.Option(50, "--max-turns", help="Maximum agent turns"),
    max_budget_usd: float | None = typer.Option(
        None, "--max-budget-usd", help="Max spend cap in USD"
    ),
    no_watch: bool = typer.Option(
        False, "--no-watch", help="Start the run and exit without streaming events"
    ),
    prompt: str | None = typer.Option(
        None, "--prompt", help="Override prompt (defaults to PROGRAM.md / domain.prompt)"
    ),
) -> None:
    """Start an agent run on the current domain (no server required)."""
    asyncio.run(
        _run_async(
            domain_override=domain,
            max_turns=max_turns,
            max_budget_usd=max_budget_usd,
            no_watch=no_watch,
            prompt_override=prompt,
        )
    )


async def _run_async(
    *,
    domain_override: str | None,
    max_turns: int,
    max_budget_usd: float | None,
    no_watch: bool,
    prompt_override: str | None,
) -> None:
    lab, settings = build_cli_lab()
    base_dir = Path(settings.storage.base_dir)

    try:
        d = await resolve_domain(lab, base_dir=base_dir, override=domain_override)
    except CLIStateError as e:
        console.print(f"[red]error:[/red] {e}")
        raise typer.Exit(code=EXIT_USER_ERROR) from e

    # Pick prompt: explicit override > PROGRAM.md > domain.prompt > friendly default
    prompt = prompt_override or load_program(d, base_dir=base_dir)
    if not prompt:
        prompt = f"Make progress on the {d.name} research domain."

    backend = create_agent_backend(settings.agent.backend)
    orchestrator = AgentOrchestrator(
        lab,
        backend,
        max_turns=max_turns,
        max_budget_usd=max_budget_usd,
        permission_mode=settings.agent.permission_mode,
        cwd=settings.agent.cwd,
    )

    try:
        run_obj = await orchestrator.start(prompt=prompt, domain_id=d.id)
    except Exception as e:
        # Phase 3 will raise TaskNotReadyError here; for now any startup failure
        # is treated as a user-actionable error.
        console.print(f"[red]failed to start run:[/red] {e}")
        raise typer.Exit(code=EXIT_TASK_NOT_READY) from e

    set_current_run_id(base_dir, run_obj.id)

    console.print(
        f"[green]▶[/green] run [bold]{run_obj.id}[/bold] started "
        f"on domain [cyan]{d.name}[/cyan] (backend={backend.name})\n"
    )

    if no_watch:
        # Fire-and-forget: kick off execute() and return. The run is persisted
        # via run_store so other processes can observe it. The task runs to
        # completion before asyncio.run() exits because we await it briefly
        # below — long-running runs should use the server, not --no-watch.
        bg = asyncio.create_task(orchestrator.execute(run_obj))
        # Give the orchestrator a tick to write the initial run state.
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(bg, timeout=0.5)
        console.print(
            f"Watching disabled. Stream later with `dojo runs show {run_obj.id}` or via the API."
        )
        return

    execute_task = asyncio.create_task(orchestrator.execute(run_obj))
    await _stream_events(run_obj, execute_task)

    # Final status line
    if run_obj.status == RunStatus.COMPLETED:
        console.print(f"\n[green]✓[/green] run completed ({len(run_obj.events)} events)")
    elif run_obj.status == RunStatus.FAILED:
        console.print(f"\n[red]✗[/red] run failed: {run_obj.error or 'unknown error'}")
        raise typer.Exit(code=EXIT_SYSTEM_ERROR)
    elif run_obj.status == RunStatus.STOPPED:
        console.print("\n[yellow]■[/yellow] run stopped")


async def _stream_events(run_obj, execute_task: asyncio.Task) -> None:
    """Print agent events to the terminal as they're produced.

    Polls `run_obj.events` (the same list orchestrator.execute() appends to).
    The orchestrator runs in the background task; we read the shared list.
    """
    seen = 0
    terminal_states = {RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.STOPPED}

    while True:
        while seen < len(run_obj.events):
            _print_event(run_obj.events[seen])
            seen += 1

        if execute_task.done() and run_obj.status in terminal_states:
            # Drain any final events that landed after the loop's last read
            while seen < len(run_obj.events):
                _print_event(run_obj.events[seen])
                seen += 1
            return

        await asyncio.sleep(0.1)


def _print_event(event: AgentEvent) -> None:
    """Render a single agent event in human-readable form."""
    et = event.event_type
    data = event.data

    if et == "text":
        console.print(data.get("text", ""), style="white")
    elif et == "tool_call":
        tool = data.get("tool", "?")
        console.print(f"  [blue]→[/blue] [bold]{tool}[/bold]", style="blue")
    elif et == "tool_result":
        tool = data.get("tool", "?")
        console.print(f"  [green]←[/green] {tool}", style="dim green")
    elif et == "error":
        console.print(f"  [red]error:[/red] {data.get('error', 'unknown')}")
    elif et == "result":
        cost = data.get("cost_usd")
        turns = data.get("turns", 0)
        bits = [f"turns={turns}"]
        if cost is not None:
            bits.append(f"cost=${cost:.4f}")
        console.print(f"\n[dim]result: {', '.join(bits)}[/dim]")
    else:
        console.print(f"  [dim]{et}[/dim]")
