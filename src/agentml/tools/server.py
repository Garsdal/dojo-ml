"""AgentML tool server — bundles all tools and adapts to target SDK."""

from __future__ import annotations

from typing import Any

from agentml.core.domain import DomainTool
from agentml.runtime.lab import LabEnvironment
from agentml.tools.base import ToolDef
from agentml.tools.domain_tools import domain_tools_to_tooldefs
from agentml.tools.experiments import create_experiment_tools
from agentml.tools.knowledge import create_knowledge_tools
from agentml.tools.tracking import create_tracking_tools


def collect_all_tools(
    lab: LabEnvironment,
    *,
    domain_tools: list[DomainTool] | None = None,
) -> list[ToolDef]:
    """Collect all AgentML tool definitions backed by a LabEnvironment.

    Returns framework-agnostic ToolDef instances — not tied to any SDK.
    Optionally includes domain-specific tools converted from DomainTool definitions.
    """
    tools = [
        *create_experiment_tools(lab),
        *create_knowledge_tools(lab),
        *create_tracking_tools(lab),
    ]

    if domain_tools:
        tools.extend(domain_tools_to_tooldefs(domain_tools))

    return tools


def create_agentml_server(lab: LabEnvironment, *, adapter: str = "claude") -> Any:
    """Create the AgentML tool server using the specified adapter.

    Args:
        lab: The LabEnvironment providing all backend services.
        adapter: Which SDK adapter to use ("claude" for now).

    Returns:
        SDK-specific server config (e.g. McpSdkServerConfig for Claude).
    """
    tools = collect_all_tools(lab)

    if adapter == "claude":
        from agentml.tools.adapters.claude import ClaudeToolAdapter

        return ClaudeToolAdapter().create_server("agentml", tools)

    msg = f"Unknown tool adapter: {adapter}"
    raise ValueError(msg)


def get_allowed_tool_names(
    lab: LabEnvironment,
    server_name: str = "agentml",
    *,
    adapter: str = "claude",
) -> list[str]:
    """Get the SDK-prefixed tool names for allowed_tools configuration.

    Args:
        lab: The LabEnvironment.
        server_name: The MCP server name.
        adapter: Which SDK adapter to use.

    Returns:
        List of prefixed tool names (e.g. ["mcp__agentml__create_experiment", ...]).
    """
    tools = collect_all_tools(lab)

    if adapter == "claude":
        from agentml.tools.adapters.claude import ClaudeToolAdapter

        return ClaudeToolAdapter().tool_names_prefixed(server_name, tools)

    return [t.name for t in tools]
