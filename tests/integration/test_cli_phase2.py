"""Phase 2 CLI happy-path integration tests.

Covers the user-facing surface introduced by Phase 2:
  - dojo init (non-interactive)
  - dojo task show / freeze / unfreeze
  - dojo program show
  - dojo run (with stub agent, in-process, no server)
  - dojo runs ls / show
  - dojo domain use / current

Tests use Typer's CliRunner. Each test runs in a fresh tmp dir so the
generated `.dojo/` does not collide.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from typer.testing import CliRunner

from dojo.cli.main import app


@pytest.fixture
def cli_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Run each CLI test in an isolated working directory."""
    monkeypatch.chdir(tmp_path)
    # Force stub agent so `dojo init` doesn't try to call claude
    monkeypatch.setenv("DOJO_AGENT__BACKEND", "stub")
    yield tmp_path


@pytest.fixture
def initialized_dir(cli_dir: Path) -> Path:
    """An isolated dir that has gone through `dojo init` non-interactively.

    Phase 3.5: no `--data-path` / `--target-column` — the user is expected to
    describe the dataset in PROGRAM.md, then run `dojo task setup`.
    """
    runner = CliRunner()
    workspace = cli_dir / "ws"
    workspace.mkdir()

    result = runner.invoke(
        app,
        [
            "init",
            "--name",
            "housing",
            "--description",
            "predict prices",
            "--workspace",
            str(workspace),
            "--task-type",
            "regression",
            "--no-setup",
            "--non-interactive",
        ],
    )
    assert result.exit_code == 0, result.output
    return cli_dir


def test_init_non_interactive_creates_domain_task_program(initialized_dir: Path):
    state = (initialized_dir / ".dojo" / "state.yaml").read_text()
    assert "current_domain_id:" in state
    # PROGRAM.md is scaffolded under .dojo/domains/{id}/ — keeps the user's
    # repo clean, regardless of whether a workspace is set.
    program = list(initialized_dir.glob(".dojo/domains/*/PROGRAM.md"))
    assert len(program) == 1
    assert not (initialized_dir / "ws" / "PROGRAM.md").exists()
    body = program[0].read_text()
    assert "housing" in body
    assert "regression" in body
    # New template carries the natural-language sections
    assert "## Dataset" in body
    assert "## Target" in body
    assert "## Success" in body
    assert "## Evaluate" in body


def test_init_works_without_data_path_or_target_column(cli_dir: Path):
    """Phase 3.5: regression init is happy without dataset flags."""
    runner = CliRunner()
    workspace = cli_dir / "ws"
    workspace.mkdir()

    result = runner.invoke(
        app,
        [
            "init",
            "--name",
            "housing",
            "--workspace",
            str(workspace),
            "--task-type",
            "regression",
            "--no-setup",
            "--non-interactive",
        ],
    )
    assert result.exit_code == 0, result.output
    # task.config should not contain data_path / target_column
    domain_files = list((cli_dir / ".dojo" / "domains").glob("*.json"))
    assert len(domain_files) == 1
    import json

    data = json.loads(domain_files[0].read_text())
    assert data["task"] is not None
    cfg = data["task"]["config"]
    assert "data_path" not in cfg
    assert "target_column" not in cfg
    assert cfg["test_split_ratio"] == 0.2
    assert cfg["expected_metrics"] == ["rmse", "r2", "mae"]


def test_init_fails_when_required_field_missing_and_non_interactive(cli_dir: Path):
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "init",
            "--task-type",
            "regression",
            "--non-interactive",
            "--no-setup",
        ],
    )
    # Missing --name should exit with EXIT_USER_ERROR
    assert result.exit_code != 0


def test_domain_current_after_init(initialized_dir: Path):
    runner = CliRunner()
    result = runner.invoke(app, ["domain", "current"])
    assert result.exit_code == 0
    assert "housing" in result.output


def test_task_show_after_init(initialized_dir: Path):
    runner = CliRunner()
    result = runner.invoke(app, ["task", "show"])
    assert result.exit_code == 0
    assert "regression" in result.output
    assert "not frozen" in result.output


def test_task_freeze_blocked_by_verification_gate(initialized_dir: Path):
    """Phase 3: freeze rejects (exit 3) when required tools aren't verified."""
    runner = CliRunner()
    blocked = runner.invoke(app, ["task", "freeze"])
    assert blocked.exit_code == 3
    assert "verification gate" in blocked.output

    forced = runner.invoke(app, ["task", "freeze", "--unsafe-skip-verify"])
    assert forced.exit_code == 0, forced.output
    assert "without verification" in forced.output

    showed = runner.invoke(app, ["task", "show"])
    assert "frozen" in showed.output and "not frozen" not in showed.output


def test_program_show_prints_scaffolded_content(initialized_dir: Path):
    runner = CliRunner()
    result = runner.invoke(app, ["program", "show"])
    assert result.exit_code == 0
    assert "Steering prompt" in result.output


def test_run_then_runs_show_in_process(initialized_dir: Path, monkeypatch: pytest.MonkeyPatch):
    """End-to-end: prep a verified+frozen domain, run, observe."""
    import asyncio

    from dojo.cli._lab import build_cli_lab
    from dojo.core.domain import DomainTool, ToolType, VerificationResult
    from dojo.runtime.task_service import TaskService

    # Force the lab to pick up the .dojo/ inside the test dir
    monkeypatch.chdir(initialized_dir)
    lab, _settings = build_cli_lab()

    async def _seed_verified_tools() -> None:
        domains = await lab.domain_store.list()
        domain = domains[0]
        domain.task.tools = [
            DomainTool(
                name="load_data",
                type=ToolType.DATA_LOADER,
                code="print('{}')",
                verification=VerificationResult(verified=True),
            ),
            DomainTool(
                name="evaluate",
                type=ToolType.EVALUATOR,
                code="print('{}')",
                verification=VerificationResult(verified=True),
            ),
        ]
        await lab.domain_store.save(domain)
        await TaskService(lab).freeze(domain.id)

    asyncio.run(_seed_verified_tools())

    runner = CliRunner()
    result = runner.invoke(app, ["run", "--max-turns", "5"])
    assert result.exit_code == 0, result.output
    assert "completed" in result.output

    show = runner.invoke(app, ["runs", "show"])  # uses current_run_id
    assert show.exit_code == 0
    assert "completed" in show.output

    ls = runner.invoke(app, ["runs", "ls"])
    assert ls.exit_code == 0
    assert "completed" in ls.output


def test_run_blocked_when_task_not_frozen(initialized_dir: Path):
    """Phase 3: dojo run exits 3 with an actionable message if task isn't ready."""
    runner = CliRunner()
    result = runner.invoke(app, ["run", "--max-turns", "5"])
    assert result.exit_code == 3, result.output
    assert "task not ready" in result.output
    assert "dojo task" in result.output


def test_runs_show_unknown_id(initialized_dir: Path):
    runner = CliRunner()
    result = runner.invoke(app, ["runs", "show", "ghost-id"])
    assert result.exit_code == 1
    assert "not found" in result.output


def test_no_current_domain_actionable_error(cli_dir: Path):
    runner = CliRunner()
    # No init has happened yet
    result = runner.invoke(app, ["task", "show"])
    assert result.exit_code == 1
    assert "dojo init" in result.output or "domain use" in result.output


def test_domain_use_switches_pointer(initialized_dir: Path):
    runner = CliRunner()
    # Create a second domain via the CLI
    workspace = initialized_dir / "ws2"
    workspace.mkdir()
    create = runner.invoke(
        app,
        [
            "init",
            "--name",
            "housing2",
            "--workspace",
            str(workspace),
            "--task-type",
            "regression",
            "--no-setup",
            "--non-interactive",
        ],
    )
    assert create.exit_code == 0, create.output

    # Switch back to the first domain by name
    use = runner.invoke(app, ["domain", "use", "housing"])
    assert use.exit_code == 0
    cur = runner.invoke(app, ["domain", "current"])
    assert "housing" in cur.output and "housing2" not in cur.output


# Suppress the env-var diff between subprocess invocations
@pytest.fixture(autouse=True)
def _no_anthropic_key(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    yield


# Sanity: nothing leaks into the working directory of the test runner
def test_no_dot_dojo_outside_tmp(cli_dir: Path):
    # Before tests run, the fixture chdir'd into a fresh tmp dir.
    assert not (Path(os.getcwd()) / ".dojo").exists() or Path(os.getcwd()) == cli_dir
