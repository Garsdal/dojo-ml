"""Claude Agent SDK backend — runs agent sessions via ClaudeSDKClient."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from agentml.agents.backend import AgentBackend
from agentml.agents.types import AgentEvent, AgentRunConfig
from agentml.tools.adapters.claude import ClaudeToolAdapter
from agentml.tools.base import ToolDef
from agentml.utils.logging import get_logger

logger = get_logger(__name__)

# Claude Code built-in tools the agent may use
BUILTIN_TOOLS = ["Bash", "Read", "Write", "Edit", "WebFetch"]


class ClaudeAgentBackend(AgentBackend):
    """Runs an agent session using the Claude Agent SDK.

    Uses ClaudeToolAdapter from v1 to convert ToolDefs -> Claude MCP tools.
    Uses ClaudeSDKClient for session management, streaming, and interruption.
    """

    def __init__(self) -> None:
        self._client: Any = None
        self._options: Any = None
        self._tool_adapter = ClaudeToolAdapter()
        self._tool_defs: list[ToolDef] = []

    async def configure(
        self,
        tool_defs: list[ToolDef],
        config: AgentRunConfig,
    ) -> None:
        """Configure the Claude agent session.

        Converts ToolDefs to Claude format via ClaudeToolAdapter,
        builds ClaudeAgentOptions with the system prompt and limits.
        """
        from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient

        self._tool_defs = tool_defs

        # Use the v1 ClaudeToolAdapter to create the MCP server
        server = self._tool_adapter.create_server("agentml", tool_defs)
        allowed_agentml = self._tool_adapter.tool_names_prefixed("agentml", tool_defs)

        self._options = ClaudeAgentOptions(
            mcp_servers={"agentml": server},
            allowed_tools=[*allowed_agentml, *BUILTIN_TOOLS],
            system_prompt=config.system_prompt,
            permission_mode=config.permission_mode,
            max_turns=config.max_turns,
            max_budget_usd=config.max_budget_usd,
            cwd=config.cwd,
        )

        self._client = ClaudeSDKClient(options=self._options)

    async def execute(self, prompt: str) -> AsyncIterator[AgentEvent]:
        """Execute the agent run, yielding events as they arrive."""
        if not self._client:
            msg = "Backend not configured — call configure() first"
            raise RuntimeError(msg)

        from claude_agent_sdk import (
            AssistantMessage,
            ResultMessage,
            TextBlock,
            ToolResultBlock,
            ToolUseBlock,
        )

        try:
            async with self._client as client:
                await client.query(prompt)

                async for message in client.receive_response():
                    events = self._message_to_events(
                        message,
                        AssistantMessage=AssistantMessage,
                        ToolUseBlock=ToolUseBlock,
                        ToolResultBlock=ToolResultBlock,
                        TextBlock=TextBlock,
                    )
                    for event in events:
                        yield event

                    # If this is the result message, yield the summary event
                    if isinstance(message, ResultMessage):
                        yield AgentEvent(
                            event_type="result",
                            data={
                                "session_id": message.session_id,
                                "turns": message.num_turns,
                                "cost_usd": message.total_cost_usd,
                                "duration_ms": message.duration_ms,
                                "is_error": message.is_error,
                            },
                        )

        except Exception as e:
            logger.error("claude_backend_error", error=str(e))
            yield AgentEvent(
                event_type="error",
                data={"error": str(e)},
            )

    async def stop(self) -> None:
        """Interrupt the Claude agent session."""
        if self._client:
            await self._client.interrupt()

    @property
    def name(self) -> str:
        return "claude"

    # --- Private helpers ---

    @staticmethod
    def _message_to_events(
        message: Any,
        *,
        AssistantMessage: type,
        ToolUseBlock: type,
        ToolResultBlock: type,
        TextBlock: type,
    ) -> list[AgentEvent]:
        """Convert a Claude SDK message to AgentEvent(s).

        A single AssistantMessage may contain multiple content blocks,
        so we return a list.
        """
        events: list[AgentEvent] = []

        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, ToolUseBlock):
                    events.append(
                        AgentEvent(
                            event_type="tool_call",
                            data={"tool": block.name, "input": block.input},
                        )
                    )
                elif isinstance(block, ToolResultBlock):
                    events.append(
                        AgentEvent(
                            event_type="tool_result",
                            data={
                                "tool_use_id": block.tool_use_id,
                                "content": block.content,
                            },
                        )
                    )
                elif isinstance(block, TextBlock):
                    events.append(
                        AgentEvent(
                            event_type="text",
                            data={"text": block.text},
                        )
                    )

        return events
