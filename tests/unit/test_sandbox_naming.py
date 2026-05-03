"""Tests for descriptive script names in LocalSandbox."""

from __future__ import annotations

from pathlib import Path

from dojo.sandbox.local import LocalSandbox, _safe_script_filename


def test_safe_filename_uses_name_when_given():
    assert _safe_script_filename("load_data", "print(1)") == "load_data.py"


def test_safe_filename_strips_unsafe_chars():
    assert _safe_script_filename("load data!", "x") == "load_data.py"
    assert _safe_script_filename("../etc/passwd", "x") == "etc_passwd.py"


def test_safe_filename_falls_back_when_unnamed():
    name = _safe_script_filename(None, "code")
    assert name.startswith("_dojo_")
    assert name.endswith(".py")


def test_safe_filename_handles_empty_name():
    assert _safe_script_filename("", "x").startswith("_dojo_")


async def test_local_sandbox_writes_named_script(tmp_path: Path):
    sandbox = LocalSandbox()
    code = "print('hi')"
    result = await sandbox.execute(
        code,
        cwd=str(tmp_path),
        name="load_data",
    )
    assert result.exit_code == 0
    assert (tmp_path / "load_data.py").exists()
    assert (tmp_path / "load_data.py").read_text() == code


async def test_local_sandbox_falls_back_to_anon_name(tmp_path: Path):
    sandbox = LocalSandbox()
    result = await sandbox.execute("print('x')", cwd=str(tmp_path))
    assert result.exit_code == 0
    matches = list(tmp_path.glob("_dojo_*.py"))
    assert len(matches) == 1
