"""Tool server — collect all ToolDefs for an agent run."""

from __future__ import annotations

from typing import Any

from dojo.core.domain import Domain
from dojo.runtime.lab import LabEnvironment
from dojo.tools.base import ToolDef
from dojo.tools.experiments import create_experiment_tools
from dojo.tools.knowledge import create_knowledge_tools
from dojo.tools.tracking import create_tracking_tools


def collect_all_tools(lab: LabEnvironment, domain: Domain | None = None) -> list[ToolDef]:
    """Collect all tool definitions for an agent run.

    Phase 4 surface (only):
    - ``run_experiment`` (per-experiment driver)
    - ``get_experiment`` / ``list_experiments`` / ``compare_experiments``
    - Knowledge tools (write_knowledge, search_knowledge, list_knowledge)
    - Tracking tools (log_metrics, log_params)

    Per-domain frozen modules (``load_data.py`` / ``evaluate.py``) are no
    longer registered as MCP tools — the runner imports them directly inside
    ``run_experiment``. The ``domain`` argument is retained for future use
    (e.g. dynamic tool injection) but no longer changes the returned list.
    """
    del domain  # currently unused — Phase 4 dropped per-domain MCP tools.
    return [
        *create_experiment_tools(lab),
        *create_knowledge_tools(lab),
        *create_tracking_tools(lab),
    ]


def create_dojo_server(lab: LabEnvironment, *, adapter: str = "claude") -> Any:
    """Create the Dojo.ml tool server using the specified adapter.

    Args:
        lab: The LabEnvironment providing all backend services.
        adapter: Which SDK adapter to use ("claude" for now).

    Returns:
        SDK-specific server config (e.g. McpSdkServerConfig for Claude).
    """
    tools = collect_all_tools(lab)

    if adapter == "claude":
        from dojo.tools.adapters.claude import ClaudeToolAdapter

        return ClaudeToolAdapter().create_server("dojo", tools)

    msg = f"Unknown tool adapter: {adapter}"
    raise ValueError(msg)


def get_allowed_tool_names(
    lab: LabEnvironment,
    server_name: str = "dojo",
    *,
    adapter: str = "claude",
) -> list[str]:
    """Get the SDK-prefixed tool names for allowed_tools configuration.

    Args:
        lab: The LabEnvironment.
        server_name: The MCP server name.
        adapter: Which SDK adapter to use.

    Returns:
        List of prefixed tool names (e.g. ["mcp__dojo__create_experiment", ...]).
    """
    tools = collect_all_tools(lab)

    if adapter == "claude":
        from dojo.tools.adapters.claude import ClaudeToolAdapter

        return ClaudeToolAdapter().tool_names_prefixed(server_name, tools)

    return [t.name for t in tools]
