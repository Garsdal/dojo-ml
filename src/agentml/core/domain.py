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


class WorkspaceSource(StrEnum):
    """How a workspace was created."""

    LOCAL = "local"
    GIT = "git"
    EMPTY = "empty"


@dataclass
class Workspace:
    """Execution environment for a domain's agent runs.

    A workspace is a persistent, pre-configured directory with
    dependencies installed. The agent runs all code here instead
    of spending API calls on environment setup.
    """

    path: str = ""
    source: WorkspaceSource = WorkspaceSource.LOCAL
    python_path: str | None = None
    env_vars: dict[str, str] = field(default_factory=dict)
    dependencies_file: str | None = None
    setup_script: str | None = None
    ready: bool = False
    git_url: str | None = None
    git_ref: str | None = None


@dataclass
class DomainTool:
    """A domain-specific tool descriptor.

    Tier 1 (executable=False): Semantic hint in the system prompt.
    The agent reads the description and example_usage and writes
    its own code.

    Tier 2 (executable=True): Actual callable MCP tool. The agent
    calls it directly and gets a structured result. The tool code
    runs in the workspace Python environment.
    """

    id: str = field(default_factory=generate_id)
    name: str = ""
    description: str = ""
    type: ToolType = ToolType.CUSTOM
    parameters: dict[str, Any] = field(default_factory=dict)
    example_usage: str = ""
    created_by: str = "human"
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    executable: bool = False
    code: str = ""
    return_description: str = ""


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
    workspace: Workspace | None = None
