"""Stub agent backend — runs a scripted experiment flow using real ToolDef handlers."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

from agentml.agents.backend import AgentBackend
from agentml.agents.types import AgentEvent, AgentRunConfig
from agentml.tools.base import ToolDef, ToolResult


class StubAgentBackend(AgentBackend):
    """Runs a scripted experiment flow using real ToolDef handlers.

    Simulates what a real agent would do:
    1. search_knowledge
    2. create_experiment
    3. complete_experiment with mock metrics
    4. log_metrics
    5. write_knowledge
    6. yield a result event

    Each step emits tool_call + tool_result events, so the UI
    and SSE pipeline see the same event shapes as with Claude.

    If custom *events* are provided at init, those are yielded
    verbatim instead (useful for unit-testing the orchestrator).
    """

    def __init__(self, events: list[AgentEvent] | None = None) -> None:
        self._events = events or []
        self._tool_defs: list[ToolDef] = []
        self._config: AgentRunConfig | None = None
        self._tools_by_name: dict[str, ToolDef] = {}
        self._configured = False

    async def configure(
        self,
        tool_defs: list[ToolDef],
        config: AgentRunConfig,
    ) -> None:
        """Store tool definitions and config for the scripted flow."""
        self._tool_defs = tool_defs
        self._config = config
        self._tools_by_name = {t.name: t for t in tool_defs}
        self._configured = True

    async def execute(self, prompt: str) -> AsyncIterator[AgentEvent]:
        """Run the scripted flow, or yield custom events if provided."""
        if self._events:
            for event in self._events:
                await asyncio.sleep(0.01)
                yield event
            return

        # --- Scripted flow using real tool handlers ---

        async def _call_tool(name: str, params: dict[str, Any]) -> ToolResult:
            """Call a tool handler and yield tool_call / tool_result events."""
            return await self._tools_by_name[name].handler(params)

        # 1. Text: announce plan
        yield AgentEvent(
            event_type="text",
            data={"text": f"Planning stub experiment for: {prompt}"},
        )
        await asyncio.sleep(0.01)

        # 2. Search knowledge
        yield AgentEvent(
            event_type="tool_call",
            data={"tool": "search_knowledge", "input": {"query": prompt, "limit": 5}},
        )
        search_result = await _call_tool("search_knowledge", {"query": prompt, "limit": 5})
        yield AgentEvent(
            event_type="tool_result",
            data={"tool": "search_knowledge", "output": search_result.data},
        )
        await asyncio.sleep(0.01)

        # 3. Create experiment (uses the domain_id from the orchestrator's run)
        domain_id = self._config.domain_id if self._config else ""
        create_params = {
            "domain_id": domain_id,
            "hypothesis": f"Stub hypothesis for: {prompt}",
            "config": {"model": "stub"},
        }
        yield AgentEvent(
            event_type="tool_call",
            data={"tool": "create_experiment", "input": create_params},
        )
        create_result = await _call_tool("create_experiment", create_params)
        experiment_id = create_result.data["experiment_id"]
        yield AgentEvent(
            event_type="tool_result",
            data={"tool": "create_experiment", "output": create_result.data},
        )
        await asyncio.sleep(0.01)

        # 4. Complete experiment with mock metrics
        metrics = {"accuracy": 0.95, "f1_score": 0.93}
        complete_params = {"experiment_id": experiment_id, "metrics": metrics}
        yield AgentEvent(
            event_type="tool_call",
            data={"tool": "complete_experiment", "input": complete_params},
        )
        complete_result = await _call_tool("complete_experiment", complete_params)
        yield AgentEvent(
            event_type="tool_result",
            data={"tool": "complete_experiment", "output": complete_result.data},
        )
        await asyncio.sleep(0.01)

        # 5. Log metrics via tracking
        log_params = {"experiment_id": experiment_id, "metrics": metrics}
        yield AgentEvent(
            event_type="tool_call",
            data={"tool": "log_metrics", "input": log_params},
        )
        log_result = await _call_tool("log_metrics", log_params)
        yield AgentEvent(
            event_type="tool_result",
            data={"tool": "log_metrics", "output": log_result.data},
        )
        await asyncio.sleep(0.01)

        # 6. Write knowledge
        knowledge_params = {
            "context": f"Task: {prompt}",
            "claim": "Stub model achieves 95% accuracy on test data.",
            "confidence": 0.85,
            "evidence_ids": [experiment_id],
        }
        yield AgentEvent(
            event_type="tool_call",
            data={"tool": "write_knowledge", "input": knowledge_params},
        )
        knowledge_result = await _call_tool("write_knowledge", knowledge_params)
        yield AgentEvent(
            event_type="tool_result",
            data={"tool": "write_knowledge", "output": knowledge_result.data},
        )
        await asyncio.sleep(0.01)

        # 7. Final text summary
        yield AgentEvent(
            event_type="text",
            data={"text": f"Stub agent completed task: {prompt}"},
        )

        # 8. Result event
        yield AgentEvent(
            event_type="result",
            data={
                "session_id": None,
                "turns": 6,
                "cost_usd": 0.0,
                "duration_ms": 100,
                "is_error": False,
            },
        )

    async def stop(self) -> None:
        """No-op — stub finishes instantly."""

    @property
    def name(self) -> str:
        return "stub"
