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
    """The sandbox writes a script whose filename is derived from `name`,
    runs it, then cleans it up — the file should NOT linger after execution
    (lingering scripts polluted the user's workspace)."""
    sandbox = LocalSandbox()
    code = "import os; print(os.path.basename(__file__))"
    result = await sandbox.execute(
        code,
        cwd=str(tmp_path),
        name="load_data",
    )
    assert result.exit_code == 0
    # Script ran with the expected filename
    assert result.stdout.strip() == "load_data.py"
    # And was cleaned up afterwards
    assert not (tmp_path / "load_data.py").exists()


async def test_local_sandbox_falls_back_to_anon_name(tmp_path: Path):
    """Without `name`, the sandbox uses an anonymous _dojo_<id>.py filename
    and still cleans it up after execution."""
    sandbox = LocalSandbox()
    result = await sandbox.execute(
        "import os; print(os.path.basename(__file__))",
        cwd=str(tmp_path),
    )
    assert result.exit_code == 0
    name = result.stdout.strip()
    assert name.startswith("_dojo_")
    assert name.endswith(".py")
    assert list(tmp_path.glob("_dojo_*.py")) == []


async def test_local_sandbox_script_dir_separates_runner_from_cwd(tmp_path: Path):
    """`script_dir` lets the runner stub land outside cwd — used by
    `run_experiment` so the dojo runner stays in `.dojo/...` while the
    subprocess runs from the user's workspace."""
    cwd_dir = tmp_path / "workspace"
    cwd_dir.mkdir()
    script_dir = tmp_path / "scratch"
    script_dir.mkdir()

    sandbox = LocalSandbox()
    result = await sandbox.execute(
        "import os; print(os.path.dirname(os.path.abspath(__file__)))",
        cwd=str(cwd_dir),
        script_dir=str(script_dir),
        name="runner",
    )
    assert result.exit_code == 0
    # The script ran from script_dir, not cwd
    assert result.stdout.strip() == str(script_dir)
    # Both dirs ended up clean
    assert list(cwd_dir.iterdir()) == []
    assert list(script_dir.iterdir()) == []
