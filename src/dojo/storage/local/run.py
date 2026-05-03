"""Local run store — one JSON file per agent run."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from dojo.agents.types import (
    AgentEvent,
    AgentRun,
    AgentRunConfig,
    AgentRunResult,
    RunStatus,
    ToolHint,
)
from dojo.interfaces.run_store import RunStore
from dojo.utils.serialization import to_json


class LocalRunStore(RunStore):
    """Persists AgentRun objects as JSON files in a local directory."""

    def __init__(self, base_dir: Path | None = None) -> None:
        self.base_dir = base_dir or Path(".dojo/runs")
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, run_id: str) -> Path:
        return self.base_dir / f"{run_id}.json"

    async def save(self, run: AgentRun) -> str:
        self._path(run.id).write_text(to_json(run))
        return run.id

    async def load(self, run_id: str) -> AgentRun | None:
        path = self._path(run_id)
        if not path.exists():
            return None
        return self._from_dict(json.loads(path.read_text()))

    async def list(self, *, domain_id: str | None = None) -> list[AgentRun]:
        runs = []
        for path in sorted(self.base_dir.glob("*.json")):
            try:
                run = self._from_dict(json.loads(path.read_text()))
                if domain_id is None or run.domain_id == domain_id:
                    runs.append(run)
            except Exception:
                pass
        return runs

    async def delete(self, run_id: str) -> bool:
        path = self._path(run_id)
        if path.exists():
            path.unlink()
            return True
        return False

    # --- Deserialization ---

    @staticmethod
    def _from_dict(data: dict[str, Any]) -> AgentRun:
        def _dt(val: str | None) -> datetime | None:
            return datetime.fromisoformat(val) if val else None

        events = [
            AgentEvent(
                id=e["id"],
                timestamp=datetime.fromisoformat(e["timestamp"]),
                event_type=e.get("event_type", ""),
                data=e.get("data", {}),
            )
            for e in data.get("events", [])
        ]

        hints = [
            ToolHint(
                name=h.get("name", ""),
                description=h.get("description", ""),
                source=h.get("source", ""),
                code_template=h.get("code_template", ""),
            )
            for h in data.get("tool_hints", [])
        ]

        config_data = data.get("config") or {}
        config = AgentRunConfig(
            system_prompt=config_data.get("system_prompt", ""),
            max_turns=config_data.get("max_turns", 50),
            max_budget_usd=config_data.get("max_budget_usd"),
            permission_mode=config_data.get("permission_mode", "acceptEdits"),
            cwd=config_data.get("cwd"),
            python_path=config_data.get("python_path"),
            domain_id=config_data.get("domain_id", ""),
        )

        result = None
        if result_data := data.get("result"):
            result = AgentRunResult(
                session_id=result_data.get("session_id"),
                total_cost_usd=result_data.get("total_cost_usd"),
                num_turns=result_data.get("num_turns", 0),
                duration_ms=result_data.get("duration_ms"),
                is_error=result_data.get("is_error", False),
                error_message=result_data.get("error_message"),
            )

        return AgentRun(
            id=data["id"],
            domain_id=data.get("domain_id", ""),
            prompt=data.get("prompt", ""),
            status=RunStatus(data.get("status", "pending")),
            events=events,
            started_at=_dt(data.get("started_at")),
            completed_at=_dt(data.get("completed_at")),
            config=config,
            result=result,
            error=data.get("error"),
            tool_hints=hints,
        )
