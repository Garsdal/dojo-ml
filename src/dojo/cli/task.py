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
from dojo.runtime.lab import LabEnvironment
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
        if d.task is None:
            console.print(
                "[red]error:[/red] domain has no task — create one first "
                "(via `dojo init` or POST /domains/{id}/task)."
            )
            raise typer.Exit(code=EXIT_USER_ERROR)
        if d.task.frozen:
            console.print("[red]error:[/red] task is frozen. Run `dojo task unfreeze` first.")
            raise typer.Exit(code=EXIT_USER_ERROR)

        prompt = build_task_generation_prompt(d, d.task, hint)

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
        console.print(f"[green]generated {len(new_tools)} tools[/green]")

        if not skip_verify:
            console.print("verifying tools against contract...")
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

        if skip_save:
            return

        d.task.tools = new_tools
        d.tools = list(new_tools)
        await lab.domain_store.save(d)
        console.print(f"[green]✓[/green] saved to domain {d.id}")

    asyncio.run(_run())


def _verify_marker(tool: Domain | object) -> str:
    """Return a colored marker for a tool's verification status."""
    v = getattr(tool, "verification", None)
    if v is None:
        return "[dim]?[/dim]"
    return "[green]✓[/green]" if v.verified else "[red]✗[/red]"


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

    Rejects (exit 3) if any required tool isn't verified. Run
    `dojo task generate` first, fix any failures, then freeze.
    """

    async def _run() -> None:
        lab, d, _ = await _resolve(override=domain)
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
                "\n  fix: run `[bold]dojo task generate[/bold]` to (re)generate "
                "and verify, then freeze."
            )
            raise typer.Exit(code=3) from exc
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
