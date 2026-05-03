"""Local sandbox — executes code via subprocess in a temp directory."""

import asyncio
import os
import re
import tempfile
import time
from pathlib import Path

from dojo.interfaces.sandbox import ExecutionResult, Sandbox

_NAME_SAFE = re.compile(r"[^a-zA-Z0-9_-]+")


def _safe_script_filename(name: str | None, code: str) -> str:
    """Pick a filename for the sandbox script.

    With ``name``, returns ``{slug}.py`` (slug stripped to a-z, A-Z, 0-9, _ , -).
    Without, falls back to a uniquish ``_dojo_<id>.py`` so concurrent runs
    don't clobber each other.
    """
    if name:
        slug = _NAME_SAFE.sub("_", name).strip("_") or "tool"
        return f"{slug}.py"
    return f"_dojo_{id(code)}.py"


class LocalSandbox(Sandbox):
    """Sandbox that executes code in a local subprocess."""

    def __init__(self, timeout: float = 300.0) -> None:
        self.timeout = timeout

    async def execute(
        self,
        code: str,
        *,
        language: str = "python",
        cwd: str | None = None,
        python_path: str | None = None,
        env_vars: dict[str, str] | None = None,
        timeout: float | None = None,
        name: str | None = None,
        script_dir: str | None = None,
    ) -> ExecutionResult:
        """Execute code in a subprocess, optionally in a workspace context.

        ``script_dir`` controls where the runner script is written. Defaults
        to ``cwd`` (or a fresh tempdir if cwd is also None). Setting
        ``script_dir`` separately lets callers run with cwd=<user's workspace>
        while keeping the dojo runner stub out of that workspace — used by
        ``run_experiment`` to drop the runner under ``.dojo/domains/{id}/runs/``.
        """
        if language != "python":
            return ExecutionResult(stderr=f"Unsupported language: {language}", exit_code=1)

        effective_timeout = timeout if timeout is not None else self.timeout
        effective_python = python_path or "python"
        work_dir = cwd or tempfile.mkdtemp()
        # Where the runner stub lands. Separated from cwd so we can write
        # under .dojo/ while running with cwd=workspace for relative imports.
        effective_script_dir = script_dir or work_dir

        script_path = Path(effective_script_dir) / _safe_script_filename(name, code)
        script_path.write_text(code)

        env = {**os.environ, **(env_vars or {})}

        start = time.monotonic()
        try:
            proc = await asyncio.create_subprocess_exec(
                effective_python,
                str(script_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=work_dir,
                env=env,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=effective_timeout)
            duration_ms = (time.monotonic() - start) * 1000

            return ExecutionResult(
                stdout=stdout.decode(),
                stderr=stderr.decode(),
                exit_code=proc.returncode or 0,
                duration_ms=duration_ms,
            )
        except TimeoutError:
            duration_ms = (time.monotonic() - start) * 1000
            return ExecutionResult(
                stderr="Execution timed out",
                exit_code=-1,
                duration_ms=duration_ms,
            )
        finally:
            # Always clean up the runner stub we wrote — leaving it behind
            # was the root cause of `__dojo_runner.py` / `verify_<tool>.py`
            # leaking into the user's workspace.
            script_path.unlink(missing_ok=True)

    async def install_packages(self, packages: list[str]) -> ExecutionResult:
        """Install packages using pip."""
        proc = await asyncio.create_subprocess_exec(
            "pip",
            "install",
            *packages,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        return ExecutionResult(
            stdout=stdout.decode(),
            stderr=stderr.decode(),
            exit_code=proc.returncode or 0,
        )

    async def cleanup(self) -> None:
        """No persistent resources to clean up in local sandbox."""
