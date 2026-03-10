"""Claude Agent SDK adapter — converts ToolDef to @tool decorated functions."""

from __future__ import annotations

from typing import Any

from agentml.tools.adapters.base import ToolAdapter
from agentml.tools.base import ToolDef, ToolResult


class ClaudeToolAdapter(ToolAdapter):
    """Converts ToolDef instances to Claude Agent SDK MCP tools.

    The Claude SDK expects tools decorated with @tool that return:
        {"content": [{"type": "text", "text": "..."}]}

    This adapter wraps our ToolDef handlers to produce that format.
    """

    def _to_claude_response(self, result: ToolResult) -> dict[str, Any]:
        """Convert a ToolResult to Claude's expected response format."""
        return {"content": [{"type": "text", "text": result.to_text()}]}

    def adapt_tool(self, tool_def: ToolDef) -> Any:
        """Convert a ToolDef to a Claude @tool decorated function.

        Uses lazy import of claude_agent_sdk so the adapter module
        can be imported without the SDK installed (for testing, etc.).
        """
        from claude_agent_sdk import tool as sdk_tool

        adapter = self

        @sdk_tool(tool_def.name, tool_def.description, tool_def.parameters)
        async def wrapped(args: dict[str, Any]) -> dict[str, Any]:
            result = await tool_def.handler(args)
            return adapter._to_claude_response(result)

        return wrapped

    def create_server(
        self,
        name: str,
        tool_defs: list[ToolDef],
        *,
        version: str = "0.1.0",
    ) -> Any:
        """Bundle tools into a Claude MCP server config.

        Returns:
            McpSdkServerConfig ready for ClaudeAgentOptions.mcp_servers.
        """
        from claude_agent_sdk import create_sdk_mcp_server

        sdk_tools = self.adapt_all(tool_defs)
        return create_sdk_mcp_server(
            name=name,
            version=version,
            tools=sdk_tools,
        )

    def tool_names_prefixed(self, server_name: str, tool_defs: list[ToolDef]) -> list[str]:
        """Return Claude's prefixed tool names: mcp__<server>__<tool>."""
        return [f"mcp__{server_name}__{td.name}" for td in tool_defs]
