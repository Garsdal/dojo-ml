"""Sandbox interface for code execution."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class ExecutionResult:
    """Result of code execution in a sandbox."""

    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    duration_ms: float = 0.0
    artifacts: list[str] = field(default_factory=list)


class Sandbox(ABC):
    """Abstract base class for sandboxed code execution."""

    @abstractmethod
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
        """Execute code in the sandbox.

        Args:
            code: The source code to execute.
            language: The programming language (default: python).
            cwd: Working directory for execution.
            python_path: Path to Python executable (uses system default if None).
            env_vars: Additional environment variables.
            timeout: Override sandbox default timeout.
            name: Optional human-readable name for the script file (e.g.
                ``"load_data"``). When set, the file is written as
                ``{name}.py``. Sanitised for safety.
            script_dir: Where to write the runner stub. Defaults to ``cwd``.
                Use this to keep the runner out of the user's workspace
                while still running with ``cwd=<workspace>``.

        Returns:
            The execution result.
        """
        ...

    @abstractmethod
    async def install_packages(self, packages: list[str]) -> ExecutionResult:
        """Install packages in the sandbox environment."""
        ...

    @abstractmethod
    async def cleanup(self) -> None:
        """Clean up sandbox resources."""
        ...
