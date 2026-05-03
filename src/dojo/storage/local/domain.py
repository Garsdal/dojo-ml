"""Local domain store — JSON file per domain."""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from dojo.core.domain import (
    Domain,
    DomainStatus,
    DomainTool,
    ToolType,
    VerificationResult,
    Workspace,
    WorkspaceSource,
)
from dojo.core.task import Direction, Task, TaskType
from dojo.interfaces.domain_store import DomainStore
from dojo.utils.serialization import to_json


class LocalDomainStore(DomainStore):
    """Persists domains as JSON files in a local directory."""

    def __init__(self, base_dir: Path | None = None) -> None:
        self.base_dir = base_dir or Path(".dojo/domains")
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, domain_id: str) -> Path:
        return self.base_dir / f"{domain_id}.json"

    async def save(self, domain: Domain) -> str:
        self._path(domain.id).write_text(to_json(domain))
        return domain.id

    async def load(self, domain_id: str) -> Domain | None:
        path = self._path(domain_id)
        if not path.exists():
            return None
        data = json.loads(path.read_text())
        return self._from_dict(data)

    async def list(self) -> list[Domain]:
        domains = []
        for path in self.base_dir.glob("*.json"):
            data = json.loads(path.read_text())
            domains.append(self._from_dict(data))
        return domains

    async def delete(self, domain_id: str) -> bool:
        path = self._path(domain_id)
        if path.exists():
            path.unlink()
            return True
        return False

    async def update(self, domain: Domain) -> str:
        return await self.save(domain)

    @staticmethod
    def _workspace_from_dict(data: dict[str, Any]) -> Workspace:
        return Workspace(
            path=data.get("path", ""),
            source=WorkspaceSource(data.get("source", "local")),
            python_path=data.get("python_path"),
            env_vars=data.get("env_vars", {}),
            dependencies_file=data.get("dependencies_file"),
            setup_script=data.get("setup_script"),
            ready=data.get("ready", False),
            git_url=data.get("git_url"),
            git_ref=data.get("git_ref"),
        )

    @staticmethod
    def _tool_from_dict(data: dict[str, Any]) -> DomainTool:
        verification = None
        if data.get("verification"):
            v = data["verification"]
            verified_at = v.get("verified_at")
            verification = VerificationResult(
                verified=v.get("verified", False),
                errors=list(v.get("errors", [])),
                sample_output=dict(v.get("sample_output", {})),
                duration_ms=v.get("duration_ms"),
                verified_at=datetime.fromisoformat(verified_at) if verified_at else None,
            )
        return DomainTool(
            id=data["id"],
            name=data.get("name", ""),
            description=data.get("description", ""),
            type=ToolType(data.get("type", "custom")),
            example_usage=data.get("example_usage", ""),
            created_by=data.get("created_by", "human"),
            created_at=datetime.fromisoformat(data["created_at"])
            if "created_at" in data
            else datetime.now(),
            code=data.get("code", ""),
            return_description=data.get("return_description", ""),
            verification=verification,
            module_filename=data.get("module_filename", ""),
            entrypoint=data.get("entrypoint", ""),
        )

    @staticmethod
    def _task_from_dict(data: dict[str, Any]) -> Task:
        tools = [LocalDomainStore._tool_from_dict(t) for t in data.get("tools", [])]
        return Task(
            id=data["id"],
            type=TaskType(data.get("type", "regression")),
            name=data.get("name", ""),
            description=data.get("description", ""),
            primary_metric=data.get("primary_metric", "rmse"),
            direction=Direction(data.get("direction", "minimize")),
            tools=tools,
            config=data.get("config", {}),
            frozen=data.get("frozen", False),
            created_at=datetime.fromisoformat(data["created_at"])
            if "created_at" in data
            else datetime.now(),
            updated_at=datetime.fromisoformat(data["updated_at"])
            if "updated_at" in data
            else datetime.now(),
        )

    @staticmethod
    def _from_dict(data: dict[str, Any]) -> Domain:
        workspace = None
        if data.get("workspace"):
            workspace = LocalDomainStore._workspace_from_dict(data["workspace"])

        task = None
        if data.get("task"):
            task = LocalDomainStore._task_from_dict(data["task"])

        return Domain(
            id=data["id"],
            name=data.get("name", ""),
            description=data.get("description", ""),
            prompt=data.get("prompt", ""),
            status=DomainStatus(data.get("status", "draft")),
            config=data.get("config", {}),
            metadata=data.get("metadata", {}),
            experiment_ids=data.get("experiment_ids", []),
            created_at=datetime.fromisoformat(data["created_at"])
            if "created_at" in data
            else datetime.now(),
            updated_at=datetime.fromisoformat(data["updated_at"])
            if "updated_at" in data
            else datetime.now(),
            workspace=workspace,
            task=task,
            program_path=data.get("program_path"),
        )
