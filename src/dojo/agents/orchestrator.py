"""Agent orchestrator — manages an agent run lifecycle, SDK-agnostic."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from dojo.agents.backend import AgentBackend
from dojo.agents.prompts import build_system_prompt
from dojo.agents.types import (
    AgentEvent,
    AgentRun,
    AgentRunConfig,
    AgentRunResult,
    RunStatus,
    ToolHint,
)
from dojo.core.domain import Domain
from dojo.runtime.lab import LabEnvironment
from dojo.runtime.program_loader import load_program
from dojo.tools.server import collect_all_tools
from dojo.utils.logging import get_logger

logger = get_logger(__name__)


class AgentOrchestrator:
    """Manages one agent run using a pluggable AgentBackend.

    The orchestrator is responsible for:
    - Building the AgentRunConfig (system prompt, limits)
    - Collecting ToolDefs from v1
    - Passing tools + config to the backend
    - Driving the execute loop and appending events to AgentRun
    - Error handling and status transitions

    It does NOT know about Claude, Copilot, or any specific SDK.
    """

    def __init__(
        self,
        lab: LabEnvironment,
        backend: AgentBackend,
        *,
        max_turns: int = 50,
        max_budget_usd: float | None = None,
        permission_mode: str = "acceptEdits",
        cwd: str | None = None,
    ) -> None:
        self.lab = lab
        self.backend = backend
        self.max_turns = max_turns
        self.max_budget_usd = max_budget_usd
        self.permission_mode = permission_mode
        self.cwd = cwd
        self._run: AgentRun | None = None

    async def start(
        self,
        prompt: str,
        *,
        domain_id: str,
        tool_hints: list[ToolHint] | None = None,
    ) -> AgentRun:
        """Prepare an agent run: create run state, configure backend.

        Does not start execution — call execute() separately
        (usually in a background task).
        """
        run = AgentRun(
            domain_id=domain_id,
            prompt=prompt,
            status=RunStatus.RUNNING,
            started_at=datetime.now(UTC),
            tool_hints=tool_hints or [],
        )
        self._run = run
        await self.lab.run_store.save(run)

        # Load domain context if available
        domain: Domain | None = None
        accumulated_knowledge: list[str] = []

        domain = await self.lab.domain_store.load(domain_id)

        if domain is not None:
            atoms = await self.lab.knowledge_linker.get_domain_knowledge(domain_id)
            accumulated_knowledge = [f"- [{a.confidence:.1f}] {a.claim}" for a in atoms[:20]]

            # PROGRAM.md (if present) overrides domain.prompt for this run.
            base_dir: Path | None = None
            if self.lab.settings is not None:
                base_dir = Path(self.lab.settings.storage.base_dir)
            program = load_program(domain, base_dir=base_dir)
            if program:
                domain.prompt = program

        # Build system prompt with domain context
        system_prompt = build_system_prompt(
            run,
            domain=domain,
            accumulated_knowledge=accumulated_knowledge,
        )

        # Build config
        config = AgentRunConfig(
            system_prompt=system_prompt,
            max_turns=self.max_turns,
            max_budget_usd=self.max_budget_usd,
            permission_mode=self.permission_mode,
            cwd=self.cwd,
            domain_id=run.domain_id,
        )
        if domain is not None and domain.workspace is not None and domain.workspace.ready:
            ws = domain.workspace
            if ws.path:
                config.cwd = ws.path
            if ws.python_path:
                config.python_path = ws.python_path
        run.config = config

        # Collect tool definitions (framework-agnostic)
        tool_defs = collect_all_tools(self.lab, domain=domain)

        # Configure the backend with tools and config
        await self.backend.configure(tool_defs, config)

        return run

    async def execute(self, run: AgentRun) -> None:
        """Execute the agent run (blocking). Call in a background task.

        Consumes the event stream from the backend and appends events to
        run.events. Writes through to run_store every _PERSIST_EVERY events
        and on every status change so other processes can observe progress.
        """
        _PERSIST_EVERY = 10
        _event_count = 0

        try:
            async for event in self.backend.execute(run.prompt):
                run.events.append(event)
                _event_count += 1

                # Handle the result event
                if event.event_type == "result":
                    result = _result_from_event(event)
                    run.result = result
                    if run.status == RunStatus.RUNNING:
                        run.status = (
                            RunStatus.FAILED if event.data.get("is_error") else RunStatus.COMPLETED
                        )
                    await self.lab.run_store.save(run)
                    _event_count = 0

                # Handle error events
                elif event.event_type == "error" and run.status == RunStatus.RUNNING:
                    run.status = RunStatus.FAILED
                    run.error = event.data.get("error", "Unknown error")
                    await self.lab.run_store.save(run)
                    _event_count = 0

                # Periodic write-through (cross-process visibility)
                elif _event_count >= _PERSIST_EVERY:
                    await self.lab.run_store.save(run)
                    _event_count = 0

            if run.status == RunStatus.RUNNING:
                run.status = RunStatus.COMPLETED
            run.completed_at = datetime.now(UTC)
            await self.lab.run_store.save(run)

        except Exception as e:
            run.status = RunStatus.FAILED
            run.error = str(e)
            run.completed_at = datetime.now(UTC)
            await self.lab.run_store.save(run)
            logger.error("agent_run_failed", run_id=run.id, error=str(e))

    async def stop(self) -> None:
        """Stop the running agent by interrupting the backend."""
        await self.backend.stop()
        if self._run:
            self._run.status = RunStatus.STOPPED
            self._run.completed_at = datetime.now(UTC)
            # Build a partial result from events collected so far
            if not self._run.result:
                tool_calls = sum(1 for e in self._run.events if e.event_type == "tool_call")
                self._run.result = AgentRunResult(
                    session_id=None,
                    num_turns=tool_calls,
                )


def _result_from_event(event: AgentEvent) -> AgentRunResult:
    """Extract AgentRunResult from a result event's data dict."""
    return AgentRunResult(
        session_id=event.data.get("session_id"),
        total_cost_usd=event.data.get("cost_usd"),
        num_turns=event.data.get("turns", 0),
        duration_ms=event.data.get("duration_ms"),
        is_error=event.data.get("is_error", False),
    )
