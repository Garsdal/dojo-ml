"""WorkspaceService — one-time workspace setup and validation."""

from __future__ import annotations

import asyncio
import os
import shutil
import sys
from pathlib import Path
from typing import Any

from dojo.core.domain import Domain, Workspace, WorkspaceSource
from dojo.utils.logging import get_logger

logger = get_logger(__name__)


class WorkspaceService:
    """Sets up and validates domain workspaces.

    A workspace is a persistent execution environment for a domain.
    Setup happens once; all agent runs reuse the prepared workspace.
    """

    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir / "workspaces"

    async def setup(self, domain: Domain) -> Workspace:
        """Prepare a workspace for a domain.

        Resolves the path, detects or creates a virtual environment,
        installs dependencies, and marks the workspace as ready.

        Args:
            domain: The domain whose workspace to set up.

        Returns:
            Updated Workspace with python_path and ready=True.

        Raises:
            ValueError: If workspace config is invalid.
            RuntimeError: If setup fails.
        """
        ws = domain.workspace
        if ws is None:
            raise ValueError(f"Domain {domain.id} has no workspace configured")

        ws_path = await self._resolve_path(domain.id, ws)
        ws.path = str(ws_path)

        if ws.setup_script:
            await self._run_setup_script(ws_path, ws.setup_script)

        python_path = await self._ensure_python_env(ws_path, ws)
        ws.python_path = python_path
        ws.ready = True

        logger.info("workspace_ready", domain_id=domain.id, path=ws.path, python=python_path)
        return ws

    async def validate(self, domain: Domain) -> dict[str, Any]:
        """Validate that a workspace is functional.

        Returns a dict with 'ok' bool and 'errors' list.
        """
        ws = domain.workspace
        if ws is None:
            return {"ok": False, "errors": ["No workspace configured"]}

        errors: list[str] = []

        # Check path exists
        ws_path = Path(ws.path)
        if not ws_path.exists():
            errors.append(f"Workspace path does not exist: {ws.path}")
            return {"ok": False, "errors": errors}

        # Check Python executable
        python = ws.python_path or "python"
        try:
            proc = await asyncio.create_subprocess_exec(
                python,
                "-c",
                "import sys; print(sys.version)",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(ws_path),
            )
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=15.0)
            if proc.returncode != 0:
                errors.append(f"Python check failed: {stderr.decode()}")
        except (TimeoutError, FileNotFoundError) as e:
            errors.append(f"Python not found or timed out: {e}")

        return {"ok": len(errors) == 0, "errors": errors}

    def get_status(self, workspace: Workspace) -> dict[str, Any]:
        """Return setup status summary for a workspace."""
        if workspace is None:
            return {"configured": False}

        ws_path = Path(workspace.path) if workspace.path else None
        return {
            "configured": True,
            "ready": workspace.ready,
            "path": workspace.path,
            "source": workspace.source.value,
            "python_path": workspace.python_path,
            "path_exists": ws_path.exists() if ws_path else False,
        }

    # --- Private helpers ---

    async def _resolve_path(self, domain_id: str, ws: Workspace) -> Path:
        """Resolve or create the workspace directory."""
        if ws.source == WorkspaceSource.LOCAL:
            path = Path(ws.path).expanduser().resolve()
            if not path.exists():
                raise RuntimeError(f"Local workspace path does not exist: {path}")
            return path

        if ws.source == WorkspaceSource.GIT:
            path = self.base_dir / domain_id
            if not path.exists():
                await self._clone_repo(ws.git_url or "", ws.git_ref, path)
            return path

        # EMPTY
        path = self.base_dir / domain_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    async def _clone_repo(self, url: str, ref: str | None, target: Path) -> None:
        """Clone a git repository to target directory."""
        self.base_dir.mkdir(parents=True, exist_ok=True)
        cmd = ["git", "clone", url, str(target)]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=120.0)
        if proc.returncode != 0:
            raise RuntimeError(f"git clone failed: {stderr.decode()}")

        if ref:
            checkout = await asyncio.create_subprocess_exec(
                "git",
                "checkout",
                ref,
                cwd=str(target),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await asyncio.wait_for(checkout.communicate(), timeout=30.0)

    async def _ensure_python_env(self, ws_path: Path, ws: Workspace) -> str:
        """Detect or create a Python virtual environment.

        Priority:
        1. Existing .venv/venv in workspace
        2. pyproject.toml → uv sync or pip install -e .
        3. requirements.txt → venv + pip install -r
        4. Nothing → return system python
        """
        # Check for existing venv
        for venv_name in (".venv", "venv"):
            venv_path = ws_path / venv_name
            if venv_path.exists():
                python = self._venv_python(venv_path)
                if Path(python).exists():
                    return python

        # Check for pyproject.toml
        if (ws_path / "pyproject.toml").exists():
            return await self._setup_with_pyproject(ws_path)

        # Check for requirements.txt
        if (ws_path / "requirements.txt").exists():
            return await self._setup_with_requirements(ws_path)

        # Fallback: system python
        return sys.executable

    async def _setup_with_pyproject(self, ws_path: Path) -> str:
        """Set up environment from pyproject.toml using uv or pip."""
        venv_path = ws_path / ".venv"

        # Try uv first (much faster)
        if shutil.which("uv"):
            proc = await asyncio.create_subprocess_exec(
                "uv",
                "sync",
                cwd=str(ws_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env={**os.environ},
            )
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=300.0)
            if proc.returncode == 0:
                python = self._venv_python(venv_path)
                if Path(python).exists():
                    return python
            else:
                logger.warning("uv_sync_failed", error=stderr.decode()[:200])

        # Fallback: pip install -e .
        venv_path.mkdir(exist_ok=True)
        await self._create_venv(venv_path)
        python = self._venv_python(venv_path)
        proc = await asyncio.create_subprocess_exec(
            python,
            "-m",
            "pip",
            "install",
            "-e",
            ".",
            cwd=str(ws_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await asyncio.wait_for(proc.communicate(), timeout=300.0)
        return python

    async def _setup_with_requirements(self, ws_path: Path) -> str:
        """Set up environment from requirements.txt."""
        venv_path = ws_path / ".venv"
        await self._create_venv(venv_path)
        python = self._venv_python(venv_path)
        proc = await asyncio.create_subprocess_exec(
            python,
            "-m",
            "pip",
            "install",
            "-r",
            "requirements.txt",
            cwd=str(ws_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await asyncio.wait_for(proc.communicate(), timeout=300.0)
        return python

    async def _create_venv(self, venv_path: Path) -> None:
        """Create a virtual environment."""
        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "venv",
            str(venv_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=60.0)
        if proc.returncode != 0:
            raise RuntimeError(f"venv creation failed: {stderr.decode()}")

    @staticmethod
    def _venv_python(venv_path: Path) -> str:
        """Return path to Python executable in a venv."""
        # Unix: .venv/bin/python
        unix_python = venv_path / "bin" / "python"
        if unix_python.exists():
            return str(unix_python)
        # Windows: .venv/Scripts/python.exe
        win_python = venv_path / "Scripts" / "python.exe"
        if win_python.exists():
            return str(win_python)
        return str(unix_python)  # Return expected path even if not yet created

    async def _run_setup_script(self, ws_path: Path, script: str) -> None:
        """Run a user-provided setup script in the workspace."""
        proc = await asyncio.create_subprocess_exec(
            "bash",
            "-c",
            script,
            cwd=str(ws_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=300.0)
        if proc.returncode != 0:
            raise RuntimeError(f"Setup script failed: {stderr.decode()}")
