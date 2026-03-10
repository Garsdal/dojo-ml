"""Framework-agnostic tool definitions for AgentML."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

# Type alias for tool handler functions
ToolHandler = Callable[[dict[str, Any]], Awaitable["ToolResult"]]


@dataclass(frozen=True)
class ToolResult:
    """Standard return type for all tool handlers.

    Framework adapters convert this to their SDK-specific format
    (e.g. Claude's {"content": [{"type": "text", "text": "..."}]}).
    """

    data: Any = None
    error: str | None = None

    @property
    def is_error(self) -> bool:
        return self.error is not None

    def to_text(self) -> str:
        """Serialize to JSON text for agent consumption."""
        if self.error:
            return json.dumps({"error": self.error}, default=str)
        return json.dumps(self.data, default=str)


@dataclass(frozen=True)
class ToolDef:
    """A framework-agnostic tool definition.

    This is the core abstraction. Each tool is defined once as a ToolDef,
    then mapped to any agent SDK via an adapter.

    Args:
        name: Unique tool name (e.g. "create_experiment")
        description: What the tool does — shown to the agent as context
        parameters: JSON Schema describing the tool's input
        handler: Async function (dict → ToolResult) implementing the tool
    """

    name: str
    description: str
    parameters: dict[str, Any]
    handler: ToolHandler


@dataclass
class ToolRegistry:
    """A simple collection of ToolDef instances.

    Not tied to any SDK — just a way to group tools for passing to an adapter.
    """

    _tools: list[ToolDef] = field(default_factory=list)

    def register(self, tool: ToolDef) -> None:
        self._tools.append(tool)

    def register_all(self, tools: list[ToolDef]) -> None:
        self._tools.extend(tools)

    @property
    def tools(self) -> list[ToolDef]:
        return list(self._tools)

    @property
    def tool_names(self) -> list[str]:
        return [t.name for t in self._tools]
