"""Stub agent backend — runs a scripted experiment flow using real ToolDef handlers."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

from dojo.agents.backend import AgentBackend
from dojo.agents.types import AgentEvent, AgentRunConfig
from dojo.tools.base import ToolDef, ToolResult


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
        """Run the scripted Phase 4 flow, or yield custom events if provided.

        Phase 4 surface uses ``run_experiment`` (a single tool that drives
        train + evaluate end-to-end). The scripted flow:

        1. ``search_knowledge`` — observability of the prior-knowledge step.
        2. ``run_experiment`` — best-effort. Trivial
           ``def train(X_train, y_train, X_test): return [0.0]*len(X_test)``.
           If the domain has no frozen task / no workspace, the call returns
           an error result and the stub keeps going so non-tracking tests
           still see the full event sequence.
        3. ``write_knowledge`` — always works (global knowledge store).
        4. ``result`` event with summary stats.
        """
        if self._events:
            for event in self._events:
                await asyncio.sleep(0.01)
                yield event
            return

        async def _call(name: str, params: dict[str, Any]) -> ToolResult:
            tool = self._tools_by_name.get(name)
            if tool is None:
                return ToolResult(error=f"tool {name!r} not registered")
            return await tool.handler(params)

        domain_id = self._config.domain_id if self._config else ""

        yield AgentEvent(
            event_type="text",
            data={"text": f"Planning stub experiment for: {prompt}"},
        )
        await asyncio.sleep(0.01)

        # 1. search_knowledge
        yield AgentEvent(
            event_type="tool_call",
            data={"tool": "search_knowledge", "input": {"query": prompt, "limit": 5}},
        )
        search_result = await _call("search_knowledge", {"query": prompt, "limit": 5})
        yield AgentEvent(
            event_type="tool_result",
            data={"tool": "search_knowledge", "output": search_result.data},
        )
        await asyncio.sleep(0.01)

        # 2. run_experiment — best-effort. The trivial train code returns a
        #    single-element prediction list so a generic regression evaluate
        #    that uses the test split has at least one point to score.
        run_params = {
            "domain_id": domain_id,
            "hypothesis": f"Stub hypothesis for: {prompt}",
            "train_code": "def train(X_train, y_train, X_test):\n    return [0.0]\n",
        }
        yield AgentEvent(
            event_type="tool_call",
            data={"tool": "run_experiment", "input": run_params},
        )
        run_result = await _call("run_experiment", run_params)
        run_output: dict[str, Any] = (
            run_result.data
            if run_result.data is not None
            else {"error": run_result.error or "no data"}
        )
        yield AgentEvent(
            event_type="tool_result",
            data={"tool": "run_experiment", "output": run_output},
        )
        experiment_id = (run_result.data or {}).get("experiment_id")
        await asyncio.sleep(0.01)

        # 3. write_knowledge (global store; works even when no domain is set up).
        knowledge_params = {
            "context": f"Task: {prompt}",
            "claim": "Stub model recorded a baseline outcome.",
            "confidence": 0.85,
            "evidence_ids": [experiment_id] if experiment_id else [],
        }
        yield AgentEvent(
            event_type="tool_call",
            data={"tool": "write_knowledge", "input": knowledge_params},
        )
        knowledge_result = await _call("write_knowledge", knowledge_params)
        yield AgentEvent(
            event_type="tool_result",
            data={"tool": "write_knowledge", "output": knowledge_result.data},
        )
        await asyncio.sleep(0.01)

        yield AgentEvent(
            event_type="text",
            data={"text": f"Stub agent completed task: {prompt}"},
        )

        yield AgentEvent(
            event_type="result",
            data={
                "session_id": None,
                "turns": 3,
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
