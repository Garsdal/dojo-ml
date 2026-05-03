"""Unit tests for runtime.program_loader."""

from __future__ import annotations

from pathlib import Path

from dojo.core.domain import Domain, Workspace, WorkspaceSource
from dojo.runtime.program_loader import (
    default_program_template,
    load_program,
    resolve_program_path,
    write_program,
)


def test_resolve_uses_program_path_when_set(tmp_path: Path):
    custom = tmp_path / "custom.md"
    domain = Domain(name="d", program_path=str(custom))
    assert resolve_program_path(domain, base_dir=tmp_path) == custom


def test_resolve_ignores_workspace_path(tmp_path: Path):
    """Workspace.path no longer steers PROGRAM.md location — it always lives
    under the dojo storage base so we don't pollute the user's repo."""
    ws_dir = tmp_path / "ws"
    ws_dir.mkdir()
    domain = Domain(
        name="d",
        workspace=Workspace(source=WorkspaceSource.LOCAL, path=str(ws_dir)),
    )
    expected = tmp_path / "domains" / domain.id / "PROGRAM.md"
    assert resolve_program_path(domain, base_dir=tmp_path) == expected


def test_resolve_falls_back_to_domain_local(tmp_path: Path):
    domain = Domain(name="d")
    expected = tmp_path / "domains" / domain.id / "PROGRAM.md"
    assert resolve_program_path(domain, base_dir=tmp_path) == expected


def test_load_returns_file_content_when_present(tmp_path: Path):
    program = tmp_path / "PROGRAM.md"
    program.write_text("Steer the agent here.\n")
    domain = Domain(name="d", prompt="ignored", program_path=str(program))
    assert load_program(domain, base_dir=tmp_path) == "Steer the agent here."


def test_load_falls_back_to_domain_prompt_when_file_missing(tmp_path: Path):
    domain = Domain(name="d", prompt="fallback prompt")
    assert load_program(domain, base_dir=tmp_path) == "fallback prompt"


def test_load_falls_back_when_file_is_empty(tmp_path: Path):
    program = tmp_path / "PROGRAM.md"
    program.write_text("   \n")
    domain = Domain(name="d", prompt="fallback", program_path=str(program))
    assert load_program(domain, base_dir=tmp_path) == "fallback"


def test_load_returns_empty_when_nothing_set(tmp_path: Path):
    domain = Domain(name="d")
    assert load_program(domain, base_dir=tmp_path) == ""


def test_write_creates_parent_dirs(tmp_path: Path):
    domain = Domain(name="d")
    written = write_program(domain, "hello", base_dir=tmp_path)
    assert written.exists()
    assert written.read_text() == "hello"


def test_default_template_contains_name_and_task(tmp_path: Path):
    from dojo.core.task import Task, TaskType

    domain = Domain(
        name="california housing",
        description="predict median house value",
        task=Task(type=TaskType.REGRESSION),
    )
    out = default_program_template(domain)
    assert "california housing" in out
    assert "predict median house value" in out
    assert "regression" in out
