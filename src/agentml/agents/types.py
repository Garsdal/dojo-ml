"""Shared types for agent sessions — SDK-agnostic."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from agentml.utils.ids import generate_id


class RunStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    STOPPED = "stopped"


@dataclass
class AgentEvent:
    """A single event in the agent run timeline.

    All backends emit events in this common format. The orchestrator and
    SSE layer only deal with AgentEvent — never SDK-specific message types.
    """

    id: str = field(default_factory=generate_id)
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    event_type: str = ""  # tool_call, tool_result, text, error, status_change, result
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentRunConfig:
    """Configuration for a single agent run — passed to AgentBackend.start().

    Framework-agnostic. Each backend interprets these fields in its own way.
    """

    system_prompt: str = ""
    max_turns: int = 50
    max_budget_usd: float | None = None
    permission_mode: str = "acceptEdits"
    cwd: str | None = None
    domain_id: str = ""  # The domain ID for the current run


@dataclass
class AgentRunResult:
    """Summary returned by AgentBackend.execute() when the run completes.

    Backends populate whichever fields they support. Fields that don't apply
    to a given backend are left as None / 0.
    """

    session_id: str | None = None
    total_cost_usd: float | None = None
    num_turns: int = 0
    duration_ms: int | None = None
    is_error: bool = False
    error_message: str | None = None


@dataclass
class ToolHint:
    """A user-provided hint about a data source or domain-specific tool."""

    name: str = ""
    description: str = ""
    source: str = ""
    code_template: str = ""


@dataclass
class AgentRun:
    """Full state of a single agent run — managed by the orchestrator."""

    id: str = field(default_factory=generate_id)
    domain_id: str = ""
    prompt: str = ""
    status: RunStatus = RunStatus.PENDING
    events: list[AgentEvent] = field(default_factory=list)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    config: AgentRunConfig = field(default_factory=AgentRunConfig)
    result: AgentRunResult | None = None
    error: str | None = None
    tool_hints: list[ToolHint] = field(default_factory=list)
