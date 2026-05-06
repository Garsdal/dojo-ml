"""`dojo init` scaffolds both PROGRAM.md and SETUP.md."""

from __future__ import annotations

from pathlib import Path

import pytest

from dojo.cli.init import _init_async


@pytest.mark.asyncio
async def test_init_writes_program_and_setup(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    await _init_async(
        name="cal_housing",
        description="predict prices",
        workspace_arg="empty",
        task_type_str="regression",
        data_path=None,
        target_column=None,
        test_split=0.2,
        tracking="file",
        agent_backend="stub",
        skip_setup=True,
        non_interactive=True,
        config_dir=tmp_path / ".dojo",
    )

    domains_dir = tmp_path / ".dojo" / "domains"
    domain_ids = [p for p in domains_dir.iterdir() if p.is_dir()]
    assert len(domain_ids) == 1
    d_dir = domain_ids[0]
    program = d_dir / "PROGRAM.md"
    setup = d_dir / "SETUP.md"
    assert program.exists() and setup.exists()
    # Strict separation of contents
    assert "## Dataset" not in program.read_text()
    assert "## Goal" not in setup.read_text()
    assert "## Dataset" in setup.read_text()
