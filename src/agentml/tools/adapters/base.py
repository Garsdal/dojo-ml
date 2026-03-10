"""Base adapter interface for converting ToolDef to SDK-specific formats."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from agentml.tools.base import ToolDef


class ToolAdapter(ABC):
    """Abstract adapter: converts ToolDef instances to SDK-specific tool objects.

    Each concrete adapter knows how to:
    1. Convert a ToolDef → SDK tool object (adapt_tool)
    2. Bundle multiple tools into a server/config (create_server)
    """

    @abstractmethod
    def adapt_tool(self, tool_def: ToolDef) -> Any:
        """Convert a single ToolDef to an SDK-specific tool object.

        Args:
            tool_def: The framework-agnostic tool definition.

        Returns:
            An SDK-specific tool object (e.g. Claude's SdkMcpTool).
        """
        ...

    def adapt_all(self, tool_defs: list[ToolDef]) -> list[Any]:
        """Convert multiple ToolDefs. Default: map adapt_tool over each."""
        return [self.adapt_tool(td) for td in tool_defs]

    @abstractmethod
    def create_server(
        self,
        name: str,
        tool_defs: list[ToolDef],
        *,
        version: str = "0.1.0",
    ) -> Any:
        """Bundle tools into an SDK-specific server configuration.

        Args:
            name: Server name identifier.
            tool_defs: Tools to include in the server.
            version: Server version string.

        Returns:
            SDK-specific server config object.
        """
        ...

    def tool_names_prefixed(self, server_name: str, tool_defs: list[ToolDef]) -> list[str]:
        """Return the SDK-prefixed tool names for an allowed_tools list.

        Default implementation returns plain names. Override for SDKs
        that use prefixes (e.g. Claude's "mcp__server__tool" pattern).
        """
        return [td.name for td in tool_defs]
