"""CLI run command — start an agent run on the current domain (in-process, no server needed).

This replaces the old HTTP-based task submission. Phase 2 of NEXT_STEPS.md fills
this out fully; for now it is a placeholder that explains the gap clearly.
"""

import typer
from rich.console import Console

console = Console()


def run(
    max_turns: int = typer.Option(50, help="Maximum agent turns"),
    max_budget_usd: float | None = typer.Option(None, help="Max spend cap in USD"),
) -> None:
    """Start an agent run on the current domain (in-process).

    Requires: a domain with a frozen Task. Set up one with `dojo init`.
    """
    console.print(
        "\n  [yellow]⚠[/yellow]  `dojo run` is being rebuilt as a first-class CLI command.\n"
        "  This will run the agent in-process without needing `dojo start`.\n\n"
        "  Until Phase 2 of NEXT_STEPS.md lands, start an agent run via:\n"
        "    [bold]dojo start[/bold]  (then use the frontend or POST /agent/run)\n"
    )
    raise typer.Exit(code=1)
