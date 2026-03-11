"""Unit tests for AgentOrchestrator — uses StubAgentBackend, no SDK needed."""

import pytest

from agentml.agents.backends.stub import StubAgentBackend
from agentml.agents.orchestrator import AgentOrchestrator
from agentml.agents.types import AgentEvent, RunStatus, ToolHint


class TestAgentOrchestrator:
    """Tests for Agent Orchestrator."""

    async def test_start_creates_running_run(self, lab):
        backend = StubAgentBackend()
        orchestrator = AgentOrchestrator(lab, backend)

        run = await orchestrator.start("test prompt")

        assert run.status == RunStatus.RUNNING
        assert run.prompt == "test prompt"
        assert run.started_at is not None
        assert run.domain_id  # Should have a generated domain ID

    async def test_start_with_custom_domain_id(self, lab):
        backend = StubAgentBackend()
        orchestrator = AgentOrchestrator(lab, backend)

        run = await orchestrator.start("test", domain_id="custom-id")

        assert run.domain_id == "custom-id"

    async def test_start_with_tool_hints(self, lab):
        backend = StubAgentBackend()
        orchestrator = AgentOrchestrator(lab, backend)

        hints = [ToolHint(name="fetch_data", description="Load dataset", source="http://test")]
        run = await orchestrator.start("test", tool_hints=hints)

        assert len(run.tool_hints) == 1
        assert run.tool_hints[0].name == "fetch_data"
        # System prompt should contain the hint
        assert "fetch_data" in run.config.system_prompt

    async def test_execute_completes_successfully(self, lab):
        backend = StubAgentBackend()
        orchestrator = AgentOrchestrator(lab, backend)

        run = await orchestrator.start("test prompt")
        await orchestrator.execute(run)

        assert run.status == RunStatus.COMPLETED
        assert run.completed_at is not None
        assert len(run.events) > 0

    async def test_execute_captures_result(self, lab):
        events = [
            AgentEvent(event_type="text", data={"text": "working"}),
            AgentEvent(
                event_type="result",
                data={
                    "session_id": "test-session",
                    "turns": 5,
                    "cost_usd": 0.25,
                    "duration_ms": 3000,
                    "is_error": False,
                },
            ),
        ]
        backend = StubAgentBackend(events=events)
        orchestrator = AgentOrchestrator(lab, backend)

        run = await orchestrator.start("test")
        await orchestrator.execute(run)

        assert run.result is not None
        assert run.result.session_id == "test-session"
        assert run.result.num_turns == 5
        assert run.result.total_cost_usd == pytest.approx(0.25)
        assert run.result.duration_ms == 3000

    async def test_execute_handles_error_event(self, lab):
        events = [
            AgentEvent(event_type="error", data={"error": "Something broke"}),
        ]
        backend = StubAgentBackend(events=events)
        orchestrator = AgentOrchestrator(lab, backend)

        run = await orchestrator.start("test")
        await orchestrator.execute(run)

        assert run.status == RunStatus.FAILED
        assert run.error == "Something broke"

    async def test_execute_handles_is_error_result(self, lab):
        events = [
            AgentEvent(
                event_type="result",
                data={"is_error": True, "turns": 1, "cost_usd": 0.01},
            ),
        ]
        backend = StubAgentBackend(events=events)
        orchestrator = AgentOrchestrator(lab, backend)

        run = await orchestrator.start("test")
        await orchestrator.execute(run)

        assert run.status == RunStatus.FAILED

    async def test_stop_sets_stopped_status(self, lab):
        backend = StubAgentBackend()
        orchestrator = AgentOrchestrator(lab, backend)

        run = await orchestrator.start("test")
        await orchestrator.stop()

        assert run.status == RunStatus.STOPPED
        assert run.completed_at is not None

    async def test_config_respects_params(self, lab):
        backend = StubAgentBackend()
        orchestrator = AgentOrchestrator(
            lab,
            backend,
            max_turns=10,
            max_budget_usd=1.5,
            permission_mode="plan",
            cwd="/tmp/test",
        )

        run = await orchestrator.start("test")

        assert run.config.max_turns == 10
        assert run.config.max_budget_usd == pytest.approx(1.5)
        assert run.config.permission_mode == "plan"
        assert run.config.cwd == "/tmp/test"

    async def test_config_includes_domain_id(self, lab):
        backend = StubAgentBackend()
        orchestrator = AgentOrchestrator(lab, backend)

        run = await orchestrator.start("test", domain_id="my-domain")

        assert run.config.domain_id == "my-domain"

    async def test_full_pipeline_creates_experiment(self, lab):
        """Orchestrator + StubAgentBackend should create a real experiment."""
        backend = StubAgentBackend()
        orchestrator = AgentOrchestrator(lab, backend)

        run = await orchestrator.start("pipeline test")
        await orchestrator.execute(run)

        assert run.status == RunStatus.COMPLETED
        experiments = await lab.experiment_store.list()
        assert len(experiments) >= 1

    async def test_full_pipeline_event_types(self, lab):
        """The default stub flow should produce the expected event types."""
        backend = StubAgentBackend()
        orchestrator = AgentOrchestrator(lab, backend)

        run = await orchestrator.start("event types test")
        await orchestrator.execute(run)

        event_types = [e.event_type for e in run.events]
        assert event_types[0] == "text"
        assert "tool_call" in event_types
        assert "tool_result" in event_types
        assert event_types[-1] == "result"
