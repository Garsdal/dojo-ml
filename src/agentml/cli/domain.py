"""Domain management CLI commands."""

from __future__ import annotations

import sys
from pathlib import Path

import typer

from agentml.core.domain import Domain, DomainStatus, Workspace, WorkspaceSource
from agentml.runtime.workspace_scanner import WorkspaceScanner
from agentml.utils.logging import get_logger

logger = get_logger(__name__)

app = typer.Typer(help="Manage research domains")


@app.command()
def create(
    name: str = typer.Option(None, "--name", "-n", help="Domain name"),
    description: str = typer.Option("", "--description", "-d", help="Domain description"),
    workspace_source: str = typer.Option(
        None, "--workspace", "-w", help="Workspace source: local, git, or empty"
    ),
    workspace_path: str = typer.Option(
        None, "--path", "-p", help="Local workspace path (for --workspace local)"
    ),
    git_url: str = typer.Option(None, "--git-url", help="Git URL (for --workspace git)"),
    no_setup: bool = typer.Option(False, "--no-setup", help="Skip workspace setup"),
    config_dir: Path = typer.Option(
        Path(".agentml"), "--config-dir", help="AgentML config directory"
    ),
) -> None:
    """Create a new research domain interactively or with options."""
    import asyncio

    asyncio.run(
        _create_domain(
            name=name,
            description=description,
            workspace_source=workspace_source,
            workspace_path=workspace_path,
            git_url=git_url,
            no_setup=no_setup,
            config_dir=config_dir,
        )
    )


async def _create_domain(
    *,
    name: str | None,
    description: str,
    workspace_source: str | None,
    workspace_path: str | None,
    git_url: str | None,
    no_setup: bool,
    config_dir: Path,
) -> None:
    from agentml.storage.local.domain import LocalDomainStore
    from agentml.runtime.workspace_service import WorkspaceService

    # Interactive prompts for missing values
    if name is None:
        name = typer.prompt("Domain name")

    if not description:
        description = typer.prompt("Description (optional)", default="")

    if workspace_source is None:
        workspace_source = typer.prompt(
            "Workspace source",
            default="local",
            prompt_suffix=" [local/git/empty]: ",
        )

    workspace: Workspace | None = None
    if workspace_source == "local":
        if workspace_path is None:
            workspace_path = typer.prompt("Workspace path (directory with your code)")
        ws_path = Path(workspace_path).expanduser().resolve()
        if not ws_path.exists():
            typer.echo(f"Error: path does not exist: {ws_path}", err=True)
            sys.exit(1)
        workspace = Workspace(
            source=WorkspaceSource.LOCAL,
            path=str(ws_path),
        )

    elif workspace_source == "git":
        if git_url is None:
            git_url = typer.prompt("Git URL")
        workspace = Workspace(
            source=WorkspaceSource.GIT,
            git_url=git_url,
            git_ref=typer.prompt("Branch/tag/ref", default="main"),
        )

    elif workspace_source == "empty":
        workspace = Workspace(source=WorkspaceSource.EMPTY)

    # Create and save domain
    domain = Domain(
        name=name,
        description=description,
        status=DomainStatus.ACTIVE,
        workspace=workspace,
    )

    domain_store = LocalDomainStore(config_dir / "domains")
    await domain_store.save(domain)
    typer.echo(f"\n✓ Domain created: {domain.id}")
    typer.echo(f"  Name: {domain.name}")

    if workspace is None:
        return

    # Scan workspace for tool suggestions
    if workspace.path and Path(workspace.path).exists():
        scanner = WorkspaceScanner()
        summary = scanner.get_summary(workspace.path)

        if summary["has_pyproject"]:
            typer.echo("  Found: pyproject.toml")
        elif summary["has_requirements"]:
            typer.echo("  Found: requirements.txt")
        if summary["has_venv"]:
            typer.echo("  Found: existing virtual environment")

        data_files = summary["data_files"]
        if data_files:
            typer.echo(f"  Found {len(data_files)} data file(s): {', '.join(data_files[:3])}")

        suggestions = scanner.scan(workspace.path)
        if suggestions:
            typer.echo(f"\n  Suggested tools ({len(suggestions)} found):")
            for s in suggestions[:5]:
                typer.echo(f"    - {s.name}: {s.description[:60]}")
            if len(suggestions) > 5:
                typer.echo(f"    ... and {len(suggestions) - 5} more")
            typer.echo(
                f"\n  Run workspace setup to install deps and finalize:\n"
                f"    POST /domains/{domain.id}/workspace/setup"
            )

    # Optionally run setup
    if workspace.source != WorkspaceSource.EMPTY and not no_setup:
        if workspace.path and Path(workspace.path).exists():
            run_setup = typer.confirm("\nSet up workspace now? (creates venv, installs deps)", default=True)
            if run_setup:
                typer.echo("Setting up workspace...")
                ws_service = WorkspaceService(config_dir)
                try:
                    updated_ws = await ws_service.setup(domain)
                    domain.workspace = updated_ws
                    await domain_store.save(domain)
                    typer.echo(f"✓ Workspace ready: {updated_ws.path}")
                    if updated_ws.python_path:
                        typer.echo(f"  Python: {updated_ws.python_path}")
                except Exception as e:
                    typer.echo(f"  Warning: setup failed: {e}", err=True)
                    typer.echo("  You can retry later via: POST /domains/{domain.id}/workspace/setup")


@app.command()
def scan(
    path: str = typer.Argument(..., help="Workspace directory to scan"),
) -> None:
    """Scan a workspace directory and show tool suggestions."""
    ws_path = Path(path).expanduser().resolve()
    if not ws_path.exists():
        typer.echo(f"Error: path does not exist: {ws_path}", err=True)
        sys.exit(1)

    scanner = WorkspaceScanner()
    summary = scanner.get_summary(str(ws_path))
    suggestions = scanner.scan(str(ws_path))

    typer.echo(f"\nWorkspace: {ws_path}")
    typer.echo(f"  Data files: {len(summary['data_files'])}")
    typer.echo(f"  Python modules: {', '.join(summary['python_modules'][:5]) or 'none'}")
    typer.echo(f"  pyproject.toml: {'yes' if summary['has_pyproject'] else 'no'}")
    typer.echo(f"  requirements.txt: {'yes' if summary['has_requirements'] else 'no'}")
    typer.echo(f"  venv: {'yes' if summary['has_venv'] else 'no'}")

    if suggestions:
        typer.echo(f"\nTool suggestions ({len(suggestions)}):")
        for s in suggestions:
            typer.echo(f"  [{s.tool_type}] {s.name}: {s.description[:70]}")
    else:
        typer.echo("\nNo tool suggestions found.")
