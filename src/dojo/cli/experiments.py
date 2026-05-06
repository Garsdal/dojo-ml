"""`dojo experiments` — list, rank, and inspect experiments for a domain."""

from __future__ import annotations

import asyncio
from enum import StrEnum
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from dojo.cli._lab import build_cli_lab
from dojo.cli.state import CLIStateError, resolve_domain
from dojo.core.experiment import Experiment
from dojo.core.state_machine import ExperimentState
from dojo.core.task import Direction, Task

console = Console()
app = typer.Typer(help="List, rank, and inspect experiments for a domain")


class SortBy(StrEnum):
    METRIC = "metric"
    CREATED = "created"


def _primary_metric_value(exp: Experiment, key: str) -> float | None:
    if exp.result is None or not exp.result.metrics:
        return None
    val = exp.result.metrics.get(key)
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _rank(experiments: list[Experiment], task: Task | None) -> list[Experiment]:
    """Sort completed experiments by the primary metric (best first).

    Failed/pending experiments are dropped from the ranking. Domains without a
    task fall back to ``created_at`` order so the command still works.
    """
    completed = [e for e in experiments if e.state == ExperimentState.COMPLETED]
    if task is None:
        return sorted(completed, key=lambda e: e.created_at, reverse=True)

    key = task.primary_metric
    reverse = task.direction == Direction.MAXIMIZE

    def _sort_key(e: Experiment) -> float:
        val = _primary_metric_value(e, key)
        # Push "no metric" to the bottom of either ordering.
        if val is None:
            return float("-inf") if reverse else float("inf")
        return val

    return sorted(completed, key=_sort_key, reverse=reverse)


@app.command("ls")
def ls(
    domain: str | None = typer.Option(
        None, "--domain", "-d", help="Domain id or name (defaults to current)"
    ),
    limit: int = typer.Option(20, "--limit", help="Max rows to show"),
    json_output: bool = typer.Option(False, "--json", help="Emit raw JSON"),
    sort_by: SortBy = typer.Option(  # noqa: B008
        SortBy.METRIC,
        "--sort",
        help="metric: completed only, ranked by primary metric. created: all experiments, newest first.",
    ),
) -> None:
    """List experiments, ranked by the task's primary metric or by creation time."""

    async def _run() -> None:
        lab, settings = build_cli_lab()
        base_dir = Path(settings.storage.base_dir)
        try:
            d = await resolve_domain(lab, base_dir=base_dir, override=domain)
        except CLIStateError as e:
            console.print(f"[red]error:[/red] {e}")
            raise typer.Exit(code=1) from e

        all_exps = await lab.experiment_store.list(domain_id=d.id)
        if sort_by == SortBy.CREATED:
            experiments = sorted(all_exps, key=lambda e: e.created_at, reverse=True)
        else:
            experiments = _rank(all_exps, d.task)
        experiments = experiments[:limit]

        if json_output:
            console.print_json(data=[_experiment_to_dict(e, d.task) for e in experiments])
            return

        if not experiments:
            if sort_by == SortBy.CREATED:
                console.print("[dim]no experiments yet[/dim]")
            else:
                failed = sum(1 for e in all_exps if e.state == ExperimentState.FAILED)
                msg = "[dim]no completed experiments yet[/dim]"
                if failed:
                    msg += f" [dim]({failed} failed)[/dim]"
                console.print(msg)
            return

        metric_key = d.task.primary_metric if d.task else "—"
        if sort_by == SortBy.CREATED:
            console.print("[dim]sorted by[/dim] [bold]created_at[/bold] [dim](newest first)[/dim]")
        else:
            direction = d.task.direction.value if d.task else "—"
            console.print(
                f"[dim]ranked by[/dim] [bold]{metric_key}[/bold] [dim]({direction})[/dim]"
            )

        table = Table(show_header=True, header_style="bold")
        table.add_column("#", justify="right")
        table.add_column("id", style="cyan")
        if sort_by == SortBy.CREATED:
            table.add_column("created", style="dim")
        table.add_column(metric_key, justify="right")
        table.add_column("state")
        table.add_column("hypothesis")
        for i, exp in enumerate(experiments, start=1):
            metric = _primary_metric_value(exp, metric_key) if d.task else None
            metric_str = f"{metric:.4f}" if metric is not None else "—"
            hypothesis = exp.hypothesis.description if exp.hypothesis else "—"
            row = [str(i), exp.id]
            if sort_by == SortBy.CREATED:
                row.append(exp.created_at.strftime("%Y-%m-%d %H:%M:%S"))
            row.extend([metric_str, exp.state.value, hypothesis[:60]])
            table.add_row(*row)
        console.print(table)

    asyncio.run(_run())


@app.command("best")
def best(
    domain: str | None = typer.Option(
        None, "--domain", "-d", help="Domain id or name (defaults to current)"
    ),
    json_output: bool = typer.Option(False, "--json", help="Emit raw JSON"),
) -> None:
    """Show the single best experiment by the task's primary metric."""

    async def _run() -> None:
        lab, settings = build_cli_lab()
        base_dir = Path(settings.storage.base_dir)
        try:
            d = await resolve_domain(lab, base_dir=base_dir, override=domain)
        except CLIStateError as e:
            console.print(f"[red]error:[/red] {e}")
            raise typer.Exit(code=1) from e

        ranked = _rank(await lab.experiment_store.list(domain_id=d.id), d.task)
        if not ranked:
            console.print("[dim]no completed experiments yet[/dim]")
            raise typer.Exit(code=0)

        winner = ranked[0]
        if json_output:
            console.print_json(data=_experiment_to_dict(winner, d.task))
            return

        _print_experiment(winner, d.task)

    asyncio.run(_run())


@app.command("show")
def show(
    experiment_id: str = typer.Argument(..., help="Experiment id"),
    json_output: bool = typer.Option(False, "--json", help="Emit raw JSON"),
) -> None:
    """Show a single experiment in full."""

    async def _run() -> None:
        lab, _ = build_cli_lab()
        exp = await lab.experiment_store.load(experiment_id)
        if exp is None:
            console.print(f"[red]error:[/red] experiment {experiment_id!r} not found")
            raise typer.Exit(code=1)
        domain = await lab.domain_store.load(exp.domain_id)
        task = domain.task if domain else None

        if json_output:
            console.print_json(data=_experiment_to_dict(exp, task))
            return

        _print_experiment(exp, task)

    asyncio.run(_run())


# --- Helpers ---------------------------------------------------------------


def _print_experiment(exp: Experiment, task: Task | None) -> None:
    console.print(f"[bold]experiment[/bold] {exp.id}")
    console.print(f"  domain: {exp.domain_id}")
    console.print(f"  state: {exp.state.value}")
    if exp.hypothesis:
        console.print(f"  hypothesis: {exp.hypothesis.description}")
        if exp.hypothesis.variables:
            console.print(f"  variables: {exp.hypothesis.variables}")
    if exp.result and exp.result.metrics:
        primary = task.primary_metric if task else None
        for k, v in exp.result.metrics.items():
            label = f"[bold]{k}[/bold]" if k == primary else k
            console.print(
                f"  {label}: {v:.4f}" if isinstance(v, int | float) else f"  {label}: {v}"
            )
    if exp.result and exp.result.code_runs:
        last = exp.result.code_runs[-1]
        console.print(f"  code: {last.code_path} (exit={last.exit_code}, {last.duration_ms:.0f}ms)")
    if exp.result and exp.result.error:
        console.print(f"  [red]error:[/red] {exp.result.error[:300]}")


def _experiment_to_dict(exp: Experiment, task: Task | None) -> dict:
    return {
        "id": exp.id,
        "domain_id": exp.domain_id,
        "state": exp.state.value,
        "hypothesis": exp.hypothesis.description if exp.hypothesis else None,
        "variables": exp.hypothesis.variables if exp.hypothesis else {},
        "metrics": exp.result.metrics if exp.result else None,
        "primary_metric": task.primary_metric if task else None,
        "primary_metric_value": (_primary_metric_value(exp, task.primary_metric) if task else None),
        "error": exp.result.error if exp.result else None,
        "created_at": exp.created_at.isoformat(),
    }
