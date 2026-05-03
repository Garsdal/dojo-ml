"""`dojo task` — manage the Task on the current domain."""

from __future__ import annotations

import asyncio
from pathlib import Path

import typer
from rich.console import Console

from dojo.agents.factory import create_agent_backend
from dojo.cli._lab import build_cli_lab
from dojo.cli.state import CLIStateError, resolve_domain
from dojo.core.domain import Domain
from dojo.core.task import TASK_TYPE_REGISTRY, Task, TaskType
from dojo.runtime.lab import LabEnvironment
from dojo.runtime.task_service import TaskFrozenError, TaskService
from dojo.tools.tool_generation import (
    build_tool_generation_prompt,
    dicts_to_domain_tools,
    parse_generated_tools,
)

console = Console()
app = typer.Typer(help="Manage the Task contract for the current domain")

EXIT_USER_ERROR = 1
EXIT_SYSTEM_ERROR = 2


# --- Resolve helper ---------------------------------------------------------


async def _resolve(*, override: str | None) -> tuple[LabEnvironment, Domain, Path]:
    lab, settings = build_cli_lab()
    base_dir = Path(settings.storage.base_dir)
    try:
        d = await resolve_domain(lab, base_dir=base_dir, override=override)
    except CLIStateError as e:
        console.print(f"[red]error:[/red] {e}")
        raise typer.Exit(code=EXIT_USER_ERROR) from e
    return lab, d, base_dir


# --- Commands --------------------------------------------------------------


@app.command("show")
def show(
    domain: str | None = typer.Option(None, "--domain", "-d", help="Domain id or name"),
) -> None:
    """Print the current domain's task (status, tools, frozen?)."""

    async def _run() -> None:
        _, d, _base = await _resolve(override=domain)
        if d.task is None:
            console.print(
                f"[yellow]domain {d.name!r} has no task[/yellow]\n"
                "Create one with `dojo init` or via the API."
            )
            raise typer.Exit(code=EXIT_USER_ERROR)
        t = d.task
        frozen_label = "[green]frozen[/green]" if t.frozen else "[yellow]not frozen[/yellow]"
        console.print(f"[bold]task[/bold] {t.id}  {frozen_label}")
        console.print(f"  type: {t.type.value}")
        console.print(f"  primary_metric: {t.primary_metric} ({t.direction.value})")
        if t.config:
            console.print("  config:")
            for k, v in t.config.items():
                console.print(f"    {k}: {v}")
        console.print(f"  tools ({len(t.tools)}):")
        for tool in t.tools:
            kind = "executable" if tool.executable else "hint"
            console.print(f"    - {tool.name} [{kind}] — {tool.description[:60]}")

    asyncio.run(_run())


@app.command("generate")
def generate(
    hint: str = typer.Option("", "--hint", help="Natural-language hint for generation"),
    domain: str | None = typer.Option(None, "--domain", "-d", help="Domain id or name"),
    skip_save: bool = typer.Option(False, "--dry-run", help="Print tools without saving them"),
) -> None:
    """Generate domain tools via the configured agent backend.

    Phase 3 will add an automatic verify step. Today this just generates and
    persists; freeze still requires `--unsafe-skip-verify`.
    """

    async def _run() -> None:
        lab, d, _ = await _resolve(override=domain)
        if d.task is None:
            console.print(
                "[red]error:[/red] domain has no task — create one first "
                "(via `dojo init` or POST /domains/{id}/task)."
            )
            raise typer.Exit(code=EXIT_USER_ERROR)
        if d.task.frozen:
            console.print("[red]error:[/red] task is frozen. Run `dojo task unfreeze` first.")
            raise typer.Exit(code=EXIT_USER_ERROR)

        prompt = _build_generation_prompt(d, d.task, hint)

        backend = create_agent_backend(lab.settings.agent.backend)
        try:
            raw = await backend.complete(prompt)
        except (AttributeError, NotImplementedError) as e:
            console.print(
                "[red]backend does not support tool generation:[/red] "
                f"{lab.settings.agent.backend} ({e})"
            )
            raise typer.Exit(code=EXIT_SYSTEM_ERROR) from e

        try:
            tool_dicts = parse_generated_tools(raw)
        except ValueError as e:
            console.print(f"[red]could not parse generated tools:[/red] {e}")
            console.print(f"\n[dim]raw output:[/dim]\n{raw[:500]}")
            raise typer.Exit(code=EXIT_SYSTEM_ERROR) from e

        new_tools = dicts_to_domain_tools(tool_dicts)
        # Mark code-bearing tools as executable so Phase 3 wiring picks them up.
        for tool, td in zip(new_tools, tool_dicts, strict=True):
            code = td.get("code") or ""
            if isinstance(code, str) and code.strip():
                tool.code = code
                tool.executable = True

        console.print(f"[green]generated {len(new_tools)} tools[/green]")
        for t in new_tools:
            kind = "executable" if t.executable else "hint"
            console.print(f"  - {t.name} [{kind}] — {t.description[:60]}")

        if skip_save:
            return

        # Persist on both the task and the domain (Phase 3 collapses to task only)
        d.task.tools = new_tools
        d.tools = list(new_tools)
        await lab.domain_store.save(d)
        console.print(f"[green]✓[/green] saved to domain {d.id}")

    asyncio.run(_run())


@app.command("freeze")
def freeze(
    domain: str | None = typer.Option(None, "--domain", "-d", help="Domain id or name"),
    unsafe_skip_verify: bool = typer.Option(
        False,
        "--unsafe-skip-verify",
        help="Phase 3 will require verification; this flag is the explicit override",
    ),
) -> None:
    """Freeze the current domain's task — required before agent runs are allowed."""

    async def _run() -> None:
        lab, d, _ = await _resolve(override=domain)
        if d.task is None:
            console.print("[red]error:[/red] domain has no task")
            raise typer.Exit(code=EXIT_USER_ERROR)

        if not unsafe_skip_verify:
            # Phase 3 will run the verifier here. Until then, require explicit ack.
            console.print(
                "[yellow]warning:[/yellow] tool verification is not yet implemented "
                "(Phase 3). Re-run with [bold]--unsafe-skip-verify[/bold] to freeze anyway."
            )
            raise typer.Exit(code=EXIT_USER_ERROR)

        await TaskService(lab).freeze(d.id)
        console.print(f"[green]✓[/green] task frozen on domain {d.name}")

    asyncio.run(_run())


@app.command("unfreeze")
def unfreeze(
    domain: str | None = typer.Option(None, "--domain", "-d", help="Domain id or name"),
) -> None:
    """Unfreeze the task to allow tool changes.

    Warning: prior experiment metrics may not be comparable to new ones if tool
    code changes.
    """

    async def _run() -> None:
        lab, d, _ = await _resolve(override=domain)
        try:
            await TaskService(lab).unfreeze(d.id)
        except (ValueError, TaskFrozenError) as e:
            console.print(f"[red]error:[/red] {e}")
            raise typer.Exit(code=EXIT_USER_ERROR) from e
        console.print(
            f"[yellow]⚠[/yellow] task unfrozen on domain {d.name} — "
            "prior metrics may not be comparable."
        )

    asyncio.run(_run())


@app.command("setup")
def setup(
    hint: str = typer.Option("", "--hint", help="Natural-language hint for generation"),
    domain: str | None = typer.Option(None, "--domain", "-d", help="Domain id or name"),
    unsafe_skip_verify: bool = typer.Option(
        False,
        "--unsafe-skip-verify",
        help="Skip verification (Phase 3 will make this gate real)",
    ),
) -> None:
    """Convenience: `generate` → (Phase 3: `verify`) → `freeze` in one shot."""
    # Generate first
    generate(hint=hint, domain=domain, skip_save=False)
    # Then freeze
    freeze(domain=domain, unsafe_skip_verify=unsafe_skip_verify)


# --- Internals --------------------------------------------------------------


def _build_generation_prompt(domain: Domain, task: Task, hint: str) -> str:
    """Build the generation prompt — registry-aware when a template exists."""
    spec = TASK_TYPE_REGISTRY.get(task.type)
    if spec is None or task.type != TaskType.REGRESSION:
        return build_tool_generation_prompt(domain, hint=hint)

    cfg = task.config
    return spec.generation_prompt_template.format(
        domain_name=domain.name,
        domain_description=domain.description or "(no description)",
        data_path=cfg.get("data_path", "(unset)"),
        target_column=cfg.get("target_column", "(unset)"),
        test_split_ratio=cfg.get("test_split_ratio", 0.2),
        feature_columns=cfg.get("feature_columns", []),
        hint_section=f"Additional hints from the user:\n{hint}\n" if hint else "",
    )
