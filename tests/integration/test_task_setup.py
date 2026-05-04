"""Integration test for `dojo task setup` — generate + verify + freeze in one shot.

Regression test for the OptionInfo bug: `setup` calling `generate` as a Python
function used to leak typer.Option default objects (truthy) into `skip_verify`,
silently skipping verification.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from typer.testing import CliRunner

from dojo.cli.main import app

# A canned tool-generation response that the verifier should accept.
# Phase 4 contract: Python modules with named entrypoints. load_data() returns
# a 4-tuple; evaluate(y_pred) returns the rmse/r2/mae dict.
_CANNED_TOOLS_JSON = """[
  {
    "name": "load_data",
    "filename": "load_data.py",
    "entrypoint": "load_data",
    "description": "Load and split a small fixture dataset",
    "type": "data_loader",
    "code": "def load_data():\\n    return [[1.0]], [[2.0]], [1.0], [2.0]\\n"
  },
  {
    "name": "evaluate",
    "filename": "evaluate.py",
    "entrypoint": "evaluate",
    "description": "Compute rmse / r2 / mae against y_test",
    "type": "evaluator",
    "code": "import math\\n\\ndef evaluate(y_pred, *, X_train, X_test, y_train, y_test):\\n    diffs = [a - b for a, b in zip(y_pred, y_test)]\\n    mse = sum(d*d for d in diffs)/len(diffs)\\n    mae = sum(abs(d) for d in diffs)/len(diffs)\\n    return {\\"rmse\\": math.sqrt(mse), \\"r2\\": 1.0, \\"mae\\": mae}\\n"
  }
]"""


class _FakeBackend:
    """Minimal backend that returns canned tools from complete()."""

    name = "fake"
    model = "fake-model"

    async def complete(self, prompt: str) -> str:
        return _CANNED_TOOLS_JSON


@pytest.fixture
def cli_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DOJO_AGENT__BACKEND", "stub")
    # Also patch the factory so the CLI sees the fake-completion backend
    import dojo.cli.task as task_cli

    monkeypatch.setattr(
        task_cli, "create_agent_backend", lambda _name, *, model=None: _FakeBackend()
    )
    yield tmp_path


@pytest.fixture
def initialized_dir(cli_dir: Path) -> Path:
    runner = CliRunner()
    workspace = cli_dir / "ws"
    workspace.mkdir()
    result = runner.invoke(
        app,
        [
            "init",
            "--name",
            "fixture",
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


def test_dojo_task_setup_runs_verification_and_freezes(initialized_dir: Path):
    """The original bug: `setup` skipped verification because of typer-OptionInfo
    leaking through `generate(...)` defaults, then freeze rejected unverified tools."""
    runner = CliRunner()
    result = runner.invoke(app, ["task", "setup"])
    assert result.exit_code == 0, result.output

    # Per-tool verification markers should be ✓ (passed), not ? (not run)
    assert "load_data" in result.output
    assert "evaluate" in result.output
    assert "task frozen" in result.output

    # Domain on disk: task is frozen, tools have verification.verified == True
    import json

    domain_files = list((initialized_dir / ".dojo" / "domains").glob("*.json"))
    assert len(domain_files) == 1
    data = json.loads(domain_files[0].read_text())
    assert data["task"]["frozen"] is True
    by_name = {t["name"]: t for t in data["task"]["tools"]}
    for name in ("load_data", "evaluate"):
        v = by_name[name].get("verification")
        assert v is not None, f"{name} has no verification block"
        assert v["verified"] is True, f"{name} should have verified=True"


def test_dojo_task_generate_then_freeze_works_separately(initialized_dir: Path):
    """The two-step path used by `task generate` + `task freeze` should match `task setup`."""
    runner = CliRunner()
    gen = runner.invoke(app, ["task", "generate"])
    assert gen.exit_code == 0, gen.output
    fz = runner.invoke(app, ["task", "freeze"])
    assert fz.exit_code == 0, fz.output


def test_dojo_task_setup_surfaces_verification_failure(
    cli_dir: Path, monkeypatch: pytest.MonkeyPatch
):
    """If the AI's tool fails the contract, freeze refuses with exit 3 + actionable hint."""
    runner = CliRunner()
    workspace = cli_dir / "ws"
    workspace.mkdir()
    init = runner.invoke(
        app,
        [
            "init",
            "--name",
            "broken",
            "--workspace",
            str(workspace),
            "--task-type",
            "regression",
            "--no-setup",
            "--non-interactive",
        ],
    )
    assert init.exit_code == 0, init.output

    bad_tools_json = """[
      {"name": "load_data", "filename": "load_data.py", "entrypoint": "load_data",
       "type": "data_loader", "description": "broken loader",
       "code": "def load_data():\\n    return [[1]]\\n"},
      {"name": "evaluate", "filename": "evaluate.py", "entrypoint": "evaluate",
       "type": "evaluator", "description": "broken evaluator",
       "code": "def evaluate(y_pred):\\n    raise RuntimeError('oops')\\n"}
    ]"""

    class _BrokenBackend:
        name = "broken"
        model = None

        async def complete(self, prompt: str) -> str:
            return bad_tools_json

    import dojo.cli.task as task_cli

    monkeypatch.setattr(
        task_cli, "create_agent_backend", lambda _name, *, model=None: _BrokenBackend()
    )

    result = runner.invoke(app, ["task", "setup"])
    assert result.exit_code == 3, result.output
    assert "verification gate failed" in result.output
    # Helpful next step points at PROGRAM.md, not the old "run dojo task generate"
    assert "PROGRAM.md" in result.output
    assert "dojo task setup" in result.output
