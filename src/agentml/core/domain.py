"""Domain model — top-level organizational unit for ML research."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from agentml.utils.ids import generate_id


class DomainStatus(StrEnum):
    """Possible statuses for a domain."""

    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class ToolType(StrEnum):
    """Types of domain-specific tools."""

    DATA_LOADER = "data_loader"
    EVALUATOR = "evaluator"
    PREPROCESSOR = "preprocessor"
    CUSTOM = "custom"


@dataclass
class DomainTool:
    """A domain-specific tool descriptor.

    Purely semantic — tells the agent what operations are available.
    The agent decides how to use them via its own code generation.
    """

    id: str = field(default_factory=generate_id)
    name: str = ""
    description: str = ""
    type: ToolType = ToolType.CUSTOM
    parameters: dict[str, Any] = field(default_factory=dict)
    example_usage: str = ""
    created_by: str = "human"
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class Domain:
    """A research domain — the top-level organizational unit."""

    id: str = field(default_factory=generate_id)
    name: str = ""
    description: str = ""
    prompt: str = ""
    status: DomainStatus = DomainStatus.DRAFT
    tools: list[DomainTool] = field(default_factory=list)
    config: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    experiment_ids: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
