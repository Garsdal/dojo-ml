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
    """An isolated dir that has gone through `dojo init` non-interactively."""
    runner = CliRunner()
    workspace = cli_dir / "ws"
    workspace.mkdir()
    data = cli_dir / "housing.csv"
    data.write_text("a,b,target\n1,2,3\n")

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
            "--data-path",
            str(data),
            "--target-column",
            "target",
            "--test-split",
            "0.2",
            "--no-setup",
            "--no-generate-tools",
            "--non-interactive",
        ],
    )
    assert result.exit_code == 0, result.output
    return cli_dir


def test_init_non_interactive_creates_domain_task_program(initialized_dir: Path):
    state = (initialized_dir / ".dojo" / "state.yaml").read_text()
    assert "current_domain_id:" in state
    # PROGRAM.md was scaffolded next to the workspace
    program = list(initialized_dir.glob("ws/PROGRAM.md"))
    assert len(program) == 1
    body = program[0].read_text()
    assert "housing" in body
    assert "regression" in body


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
            "--no-generate-tools",
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


def test_task_freeze_requires_unsafe_flag(initialized_dir: Path):
    runner = CliRunner()
    blocked = runner.invoke(app, ["task", "freeze"])
    assert blocked.exit_code == 1
    assert "verification" in blocked.output

    forced = runner.invoke(app, ["task", "freeze", "--unsafe-skip-verify"])
    assert forced.exit_code == 0, forced.output

    showed = runner.invoke(app, ["task", "show"])
    assert "frozen" in showed.output and "not frozen" not in showed.output


def test_program_show_prints_scaffolded_content(initialized_dir: Path):
    runner = CliRunner()
    result = runner.invoke(app, ["program", "show"])
    assert result.exit_code == 0
    assert "Steering prompt" in result.output


def test_run_then_runs_show_in_process(initialized_dir: Path):
    runner = CliRunner()
    # Stub backend doesn't require a frozen task today (Phase 3 will gate it).
    result = runner.invoke(app, ["run", "--max-turns", "5"])
    assert result.exit_code == 0, result.output
    assert "completed" in result.output

    show = runner.invoke(app, ["runs", "show"])  # uses current_run_id
    assert show.exit_code == 0
    assert "completed" in show.output

    ls = runner.invoke(app, ["runs", "ls"])
    assert ls.exit_code == 0
    # status column should show 'completed'
    assert "completed" in ls.output


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
    data = initialized_dir / "data2.csv"
    data.write_text("a,target\n1,2\n")
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
            "--data-path",
            str(data),
            "--target-column",
            "target",
            "--no-setup",
            "--no-generate-tools",
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
