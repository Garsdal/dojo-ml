"""Local sandbox — executes code via subprocess in a temp directory."""

import asyncio
import os
import tempfile
import time
from pathlib import Path

from agentml.interfaces.sandbox import ExecutionResult, Sandbox


class LocalSandbox(Sandbox):
    """Sandbox that executes code in a local subprocess."""

    def __init__(self, timeout: float = 30.0) -> None:
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
    ) -> ExecutionResult:
        """Execute code in a subprocess, optionally in a workspace context."""
        if language != "python":
            return ExecutionResult(stderr=f"Unsupported language: {language}", exit_code=1)

        effective_timeout = timeout if timeout is not None else self.timeout
        effective_python = python_path or "python"
        work_dir = cwd or tempfile.mkdtemp()

        script_path = Path(work_dir) / f"_agentml_{id(code)}.py"
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
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=effective_timeout
            )
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
            # Clean up the temp script file (artifacts are stored separately)
            if not cwd:
                # Only auto-cleanup temp scripts in temp dirs
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
