"""`dojo init` — single entrypoint that walks a user from empty dir to ready-to-run.

Interactive by default; every prompt has a flag for non-interactive use.
Steps:
  1. Bootstrap config (.dojo/config.yaml)
  2. Create the Domain + workspace (reuses domain.create logic)
  3. Scaffold PROGRAM.md
  4. Create the Task (regression-only today)
  5. Generate tools (verification deferred to Phase 3)
  6. Set current_domain_id
  7. Print next steps
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import typer
from rich.console import Console

from dojo.cli._lab import build_cli_lab
from dojo.cli.config import config_init
from dojo.cli.state import set_current_domain_id
from dojo.core.domain import (
    Domain,
    DomainStatus,
    Workspace,
    WorkspaceSource,
)
from dojo.core.task import TaskType
from dojo.runtime.program_loader import default_program_template, write_program
from dojo.runtime.task_service import TaskService
from dojo.runtime.tool_verifier import verify_required_tools
from dojo.runtime.workspace_service import WorkspaceService
from dojo.tools.tool_generation import (
    build_task_generation_prompt,
    dicts_to_domain_tools,
    parse_generated_tools,
)

console = Console()

EXIT_USER_ERROR = 1
EXIT_SYSTEM_ERROR = 2


def init(
    name: str | None = typer.Option(None, "--name", help="Domain name"),
    description: str = typer.Option("", "--description", help="One-line description"),
    workspace: str = typer.Option(
        ".", "--workspace", help="Local workspace path (or 'empty' for a fresh dir)"
    ),
    task_type: str = typer.Option("regression", "--task-type", help="Task type"),
    data_path: str | None = typer.Option(None, "--data-path", help="Path to dataset"),
    target_column: str | None = typer.Option(
        None, "--target-column", help="Target column for regression"
    ),
    test_split: float = typer.Option(0.2, "--test-split", help="Test split ratio for regression"),
    tracking: str | None = typer.Option(
        None, "--tracking", help="Tracking backend (file | mlflow)"
    ),
    agent_backend: str | None = typer.Option(
        None, "--agent-backend", help="Agent backend (claude | stub)"
    ),
    skip_setup: bool = typer.Option(
        False, "--no-setup", help="Skip workspace setup (no venv install)"
    ),
    skip_generate: bool = typer.Option(
        False, "--no-generate-tools", help="Skip AI tool generation"
    ),
    non_interactive: bool = typer.Option(
        False, "--non-interactive", help="Fail (don't prompt) if any value is missing"
    ),
    config_dir: Path = typer.Option(  # noqa: B008
        Path(".dojo"), "--config-dir", help="Dojo state directory"
    ),
) -> None:
    """Interactive setup wizard for a new domain."""
    asyncio.run(
        _init_async(
            name=name,
            description=description,
            workspace_arg=workspace,
            task_type_str=task_type,
            data_path=data_path,
            target_column=target_column,
            test_split=test_split,
            tracking=tracking,
            agent_backend=agent_backend,
            skip_setup=skip_setup,
            skip_generate=skip_generate,
            non_interactive=non_interactive,
            config_dir=config_dir,
        )
    )


# ---------------------------------------------------------------------------
# Implementation
# ---------------------------------------------------------------------------


def _ask(prompt: str, *, default: str | None = None, non_interactive: bool) -> str:
    if non_interactive:
        if default is None:
            console.print(f"[red]error:[/red] missing value for {prompt!r}")
            sys.exit(EXIT_USER_ERROR)
        return default
    return typer.prompt(prompt, default=default if default is not None else "")


async def _init_async(
    *,
    name: str | None,
    description: str,
    workspace_arg: str,
    task_type_str: str,
    data_path: str | None,
    target_column: str | None,
    test_split: float,
    tracking: str | None,
    agent_backend: str | None,
    skip_setup: bool,
    skip_generate: bool,
    non_interactive: bool,
    config_dir: Path,
) -> None:
    # ---- 1. Config bootstrap -------------------------------------------------
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = config_dir / "config.yaml"
    if not config_path.exists():
        # Reuse the existing CLI helper — writes the default YAML.
        config_init()

    # Honor optional flags by patching after default write
    if tracking or agent_backend:
        _patch_config(config_path, tracking=tracking, agent_backend=agent_backend)

    lab, settings = build_cli_lab()

    # ---- 2. Domain + workspace ----------------------------------------------
    if name is None:
        name = _ask("Domain name", default=None, non_interactive=non_interactive)

    if not description:
        description = _ask("Description (optional)", default="", non_interactive=non_interactive)

    workspace_obj = _build_workspace(workspace_arg)
    domain = Domain(
        name=name,
        description=description,
        status=DomainStatus.ACTIVE,
        workspace=workspace_obj,
    )
    await lab.domain_store.save(domain)
    console.print(f"[green]✓[/green] domain created: {domain.id} ({domain.name})")

    if (
        not skip_setup
        and workspace_obj is not None
        and workspace_obj.source != WorkspaceSource.EMPTY
        and workspace_obj.path
    ):
        console.print("Setting up workspace (venv + deps)...")
        ws_service = WorkspaceService(Path(settings.storage.base_dir))
        try:
            updated = await ws_service.setup(domain)
            domain.workspace = updated
            await lab.domain_store.save(domain)
            console.print(f"[green]✓[/green] workspace ready: {updated.path}")
        except Exception as e:
            console.print(f"[yellow]warning:[/yellow] workspace setup failed: {e}")
            console.print(
                f"Continuing — fix manually or rerun `POST /domains/{domain.id}/workspace/setup`"
            )

    # ---- 3. Task creation (must precede PROGRAM.md so template knows the type)
    try:
        ttype = TaskType(task_type_str)
    except ValueError as e:
        console.print(
            f"[red]error:[/red] unsupported task type {task_type_str!r}. Supported: regression"
        )
        raise typer.Exit(code=EXIT_USER_ERROR) from e

    if ttype == TaskType.REGRESSION:
        if data_path is None:
            data_path = _ask(
                "Path to the dataset (CSV)",
                default=None,
                non_interactive=non_interactive,
            )
        if target_column is None:
            target_column = _ask(
                "Target column name",
                default=None,
                non_interactive=non_interactive,
            )

    task_config: dict = {}
    if ttype == TaskType.REGRESSION:
        task_config = {
            "data_path": str(Path(data_path).expanduser()) if data_path else "",
            "target_column": target_column or "",
            "test_split_ratio": test_split,
        }

    task_svc = TaskService(lab)
    task = await task_svc.create(
        domain.id, task_type=ttype, name=f"{ttype.value} task", config=task_config
    )
    console.print(f"[green]✓[/green] task created: {task.id} ({task.type.value})")

    # Reload so domain.task is populated for the template
    domain = await lab.domain_store.load(domain.id)
    assert domain is not None  # just saved

    # ---- 4. PROGRAM.md scaffold (after task so the template knows the type) -
    program_path = write_program(
        domain,
        default_program_template(domain),
        base_dir=Path(settings.storage.base_dir),
    )
    domain.program_path = str(program_path)
    await lab.domain_store.save(domain)
    console.print(f"[green]✓[/green] PROGRAM.md scaffolded at {program_path}")

    # ---- 5. Tool generation (Phase 2: no verification) ----------------------
    if not skip_generate:
        await _generate_tools(lab, domain, settings)
    else:
        console.print("[yellow]skipped[/yellow] tool generation (--no-generate-tools)")

    # ---- 6. Set current_domain_id -------------------------------------------
    set_current_domain_id(Path(settings.storage.base_dir), domain.id)

    # ---- 7. Next steps -------------------------------------------------------
    console.print()
    console.print("[bold green]ready[/bold green] — next steps:")
    console.print(f"  1. edit [cyan]{program_path}[/cyan] to steer the agent")
    console.print(
        "  2. run `[bold]dojo task setup --unsafe-skip-verify[/bold]` "
        "to (re)generate + freeze tools"
    )
    console.print("  3. run `[bold]dojo run[/bold]` to start the agent")
    console.print(
        "\n[dim]Note:[/dim] tool [bold]verification[/bold] is Phase 3. Today "
        "freezing requires `--unsafe-skip-verify`."
    )


def _build_workspace(arg: str) -> Workspace | None:
    """Convert the --workspace flag into a Workspace dataclass."""
    if arg.lower() == "empty":
        return Workspace(source=WorkspaceSource.EMPTY)
    path = Path(arg).expanduser().resolve()
    if not path.exists():
        console.print(f"[red]error:[/red] workspace path does not exist: {path}")
        raise typer.Exit(code=EXIT_USER_ERROR)
    return Workspace(source=WorkspaceSource.LOCAL, path=str(path))


async def _generate_tools(lab, domain: Domain, settings) -> None:
    """Generate tools using the configured agent backend; verify and persist."""
    from dojo.agents.factory import create_agent_backend

    if domain.task is None:
        return

    prompt = build_task_generation_prompt(domain, domain.task, hint="")
    backend = create_agent_backend(settings.agent.backend)

    try:
        raw = await backend.complete(prompt)
    except (AttributeError, NotImplementedError):
        console.print(
            f"[yellow]skip:[/yellow] backend {settings.agent.backend} "
            "doesn't support tool generation; you can do it later "
            "with `dojo task generate`."
        )
        return
    except Exception as e:
        console.print(f"[yellow]warning:[/yellow] tool generation failed: {e}")
        return

    try:
        tool_dicts = parse_generated_tools(raw)
    except ValueError as e:
        console.print(
            f"[yellow]warning:[/yellow] could not parse tool output: {e}\n"
            "[dim]Run `dojo task generate` to retry.[/dim]"
        )
        return

    tools = dicts_to_domain_tools(tool_dicts)

    console.print("verifying tools against contract...")
    await verify_required_tools(tools, domain.task, sandbox=lab.sandbox, workspace=domain.workspace)

    domain.task.tools = tools
    domain.tools = list(tools)
    await lab.domain_store.save(domain)

    pass_count = sum(1 for t in tools if t.verification and t.verification.verified)
    console.print(
        f"[green]✓[/green] generated {len(tools)} tools "
        f"({pass_count} verified, {len(tools) - pass_count} unverified)"
    )


def _patch_config(config_path: Path, *, tracking: str | None, agent_backend: str | None) -> None:
    """Patch tracking backend / agent backend in the YAML config."""
    import yaml

    data = yaml.safe_load(config_path.read_text()) or {}
    if tracking:
        data.setdefault("tracking", {})["backend"] = tracking
    if agent_backend:
        data.setdefault("agent", {})["backend"] = agent_backend
    config_path.write_text(yaml.safe_dump(data, sort_keys=True))
