"""`dojo task` — manage the Task on the current domain."""

from __future__ import annotations

import asyncio
from pathlib import Path

import typer
from rich.console import Console

from dojo.agents.factory import create_agent_backend
from dojo.cli._lab import build_cli_lab
from dojo.cli.state import CLIStateError, resolve_domain
from dojo.core.domain import Domain, DomainTool
from dojo.runtime.lab import LabEnvironment
from dojo.runtime.program_loader import load_program
from dojo.runtime.task_service import (
    TaskFrozenError,
    TaskService,
    TaskVerificationError,
)
from dojo.runtime.tool_verifier import verify_required_tools
from dojo.tools.tool_generation import (
    build_task_generation_prompt,
    dicts_to_domain_tools,
    parse_generated_tools,
)

console = Console()
app = typer.Typer(help="Manage the Task contract for the current domain")

EXIT_USER_ERROR = 1
EXIT_SYSTEM_ERROR = 2
EXIT_GATE = 3


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
            mark = _verify_marker(tool)
            console.print(f"    {mark} {tool.name} [{kind}] — {tool.description[:60]}")

    asyncio.run(_run())


@app.command("generate")
def generate(
    hint: str = typer.Option("", "--hint", help="Natural-language hint for generation"),
    domain: str | None = typer.Option(None, "--domain", "-d", help="Domain id or name"),
    skip_save: bool = typer.Option(False, "--dry-run", help="Print tools without saving them"),
    skip_verify: bool = typer.Option(
        False, "--no-verify", help="Skip tool verification (faster, but blocks freeze)"
    ),
) -> None:
    """Generate domain tools via the configured agent backend, verify, persist.

    Each generated tool is run against its ToolContract via the sandbox.
    Verification status is shown per tool and persisted alongside the tool —
    `dojo task freeze` will then check it.
    """

    async def _run() -> None:
        lab, d, _ = await _resolve(override=domain)
        await _do_generate(lab, d, hint=hint, verify=not skip_verify, save=not skip_save)

    asyncio.run(_run())


@app.command("freeze")
def freeze(
    domain: str | None = typer.Option(None, "--domain", "-d", help="Domain id or name"),
    unsafe_skip_verify: bool = typer.Option(
        False,
        "--unsafe-skip-verify",
        help="Skip the verification gate (rare — use only when the user accepts the risk)",
    ),
) -> None:
    """Freeze the current domain's task — required before agent runs are allowed.

    Rejects (exit 3) if any required tool isn't verified. Edit `PROGRAM.md`
    (or pass --hint to generate) and re-run `dojo task setup`.
    """

    async def _run() -> None:
        lab, d, _ = await _resolve(override=domain)
        await _do_freeze(lab, d, unsafe_skip_verify=unsafe_skip_verify)

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
        help="Freeze even if verification fails (rare — accepts the risk)",
    ),
) -> None:
    """One-shot: generate tools from PROGRAM.md, verify them, freeze the task."""

    async def _run() -> None:
        lab, d, _ = await _resolve(override=domain)
        await _do_generate(lab, d, hint=hint, verify=True, save=True)
        # Reload so freeze sees the just-saved tools
        d_after = await lab.domain_store.load(d.id)
        assert d_after is not None
        await _do_freeze(lab, d_after, unsafe_skip_verify=unsafe_skip_verify)

    asyncio.run(_run())


# --- Helpers ---------------------------------------------------------------


async def _do_generate(
    lab: LabEnvironment,
    d: Domain,
    *,
    hint: str,
    verify: bool,
    save: bool,
) -> list[DomainTool]:
    """Generate (and optionally verify + persist) tools for the domain's task.

    Shared by `dojo task generate` and `dojo task setup`. Keeping this as a
    plain async function avoids the typer-OptionInfo trap that bites if one
    CLI command calls another as a Python function.
    """
    if d.task is None:
        console.print(
            "[red]error:[/red] domain has no task — create one first "
            "(via `dojo init` or POST /domains/{id}/task)."
        )
        raise typer.Exit(code=EXIT_USER_ERROR)
    if d.task.frozen:
        console.print("[red]error:[/red] task is frozen. Run `dojo task unfreeze` first.")
        raise typer.Exit(code=EXIT_USER_ERROR)

    program_md = load_program(d, base_dir=Path(lab.settings.storage.base_dir))
    prompt = build_task_generation_prompt(d, d.task, hint, program_md=program_md)
    backend = create_agent_backend(
        lab.settings.agent.backend,
        model=lab.settings.agent.tool_generation_model,
    )

    label = f"{backend.name} ({backend.model})" if backend.model else backend.name
    console.print(
        f"[dim]using[/dim] [bold]{label}[/bold] [dim]to generate load_data + evaluate"
        " (this normally takes 15-30s)[/dim]"
    )
    with console.status(
        f"[bold]asking {label}...[/bold]",
        spinner="dots",
    ):
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
    console.print(f"[green]generated {len(new_tools)} tools[/green]")

    if verify:
        with console.status(
            "[bold]verifying tools against the regression contract...[/bold]",
            spinner="dots",
        ):
            await verify_required_tools(
                new_tools, d.task, sandbox=lab.sandbox, workspace=d.workspace
            )

    for t in new_tools:
        kind = "executable" if t.executable else "hint"
        mark = _verify_marker(t)
        console.print(f"  {mark} {t.name} [{kind}] — {t.description[:60]}")
        if t.verification and not t.verification.verified:
            for err in t.verification.errors:
                console.print(f"      [red]·[/red] {err}")

    if not save:
        return new_tools

    d.task.tools = new_tools
    d.tools = list(new_tools)
    await lab.domain_store.save(d)
    console.print(f"[green]✓[/green] saved to domain {d.id}")
    return new_tools


async def _do_freeze(lab: LabEnvironment, d: Domain, *, unsafe_skip_verify: bool) -> None:
    """Freeze a domain's task with proper error surfacing.

    Shared by `dojo task freeze` and `dojo task setup`.
    """
    if d.task is None:
        console.print("[red]error:[/red] domain has no task")
        raise typer.Exit(code=EXIT_USER_ERROR)

    try:
        await TaskService(lab).freeze(d.id, skip_verification=unsafe_skip_verify)
    except TaskVerificationError as exc:
        console.print("[red]✗ task cannot be frozen — verification gate failed:[/red]")
        for err in exc.errors:
            console.print(f"  · {err}")
        console.print(
            "\n  fix: edit [cyan]PROGRAM.md[/cyan] (or pass --hint), then re-run "
            "[bold]dojo task setup[/bold]."
        )
        raise typer.Exit(code=EXIT_GATE) from exc
    except (ValueError, TaskFrozenError) as exc:
        console.print(f"[red]error:[/red] {exc}")
        raise typer.Exit(code=EXIT_USER_ERROR) from exc

    if unsafe_skip_verify:
        console.print(
            f"[yellow]⚠[/yellow] task frozen on domain {d.name} "
            "[bold]without verification[/bold] (--unsafe-skip-verify)"
        )
    else:
        console.print(f"[green]✓[/green] task frozen on domain {d.name}")


def _verify_marker(tool: DomainTool | object) -> str:
    """Return a coloured marker for a tool's verification status."""
    v = getattr(tool, "verification", None)
    if v is None:
        return "[dim]?[/dim]"
    return "[green]✓[/green]" if v.verified else "[red]✗[/red]"
