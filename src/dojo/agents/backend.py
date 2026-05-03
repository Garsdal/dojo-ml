"""Agent backend interface — the port for agent session execution."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

from dojo.agents.types import AgentEvent, AgentRunConfig
from dojo.tools.base import ToolDef


class AgentBackend(ABC):
    """Abstract interface for running an agent session.

    Each concrete backend (Claude, Copilot, etc.) implements this interface.
    The AgentOrchestrator delegates all SDK-specific logic here.

    Lifecycle:
        1. configure() — set up the backend with tools, prompt, and config
        2. execute()   — run the agent; yields AgentEvents as they happen
        3. stop()      — interrupt a running session (if supported)
    """

    @abstractmethod
    async def configure(
        self,
        tool_defs: list[ToolDef],
        config: AgentRunConfig,
    ) -> None:
        """Configure the backend for a run.

        This is called once before execute(). The backend should:
        - Adapt tool_defs to its SDK format (using the appropriate ToolAdapter)
        - Build any SDK-specific client/session configuration
        - Prepare to accept a prompt via execute()

        Args:
            tool_defs: Framework-agnostic tool definitions from v1.
            config: Run configuration (system prompt, limits, etc.).
        """
        ...

    @abstractmethod
    async def execute(self, prompt: str) -> AsyncIterator[AgentEvent]:
        """Execute the agent with the given prompt.

        Yields AgentEvent instances as the agent works. The orchestrator
        appends these to AgentRun.events and streams them via SSE.

        When the agent finishes (or errors), should yield a final event
        with event_type="result" containing the AgentRunResult as data.

        Args:
            prompt: The user's research prompt.

        Yields:
            AgentEvent instances (tool_call, tool_result, text, result, etc.)
        """
        ...

    @abstractmethod
    async def stop(self) -> None:
        """Interrupt a running agent session.

        Should be safe to call even if the agent has already stopped.
        """
        ...

    async def complete(self, prompt: str) -> str:
        """Simple one-shot completion (no tool use).

        Used for structured generation tasks like tool generation.
        Backends that support direct completions should override this.

        Args:
            prompt: The prompt to complete.

        Returns:
            The completion text.

        Raises:
            NotImplementedError: If the backend doesn't support completions.
        """
        raise NotImplementedError(f"{self.name} does not support direct completions")

    @property
    def name(self) -> str:
        """Human-readable backend name (e.g. 'claude', 'copilot')."""
        return self.__class__.__name__

    @property
    def model(self) -> str | None:
        """Model id used by ``complete()``, when known. None means default.

        Surfaced so the CLI can show "asking claude (sonnet-4-6) ..." in the
        spinner. Backends that don't pin a model just return None.
        """
        return None
