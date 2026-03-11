"""Unit tests for AgentBackend, StubAgentBackend, and factory."""

import pytest

from agentml.agents.backend import AgentBackend
from agentml.agents.backends.stub import StubAgentBackend
from agentml.agents.factory import create_agent_backend
from agentml.agents.types import AgentEvent, AgentRunConfig
from agentml.tools.server import collect_all_tools


class TestStubAgentBackend:
    """Tests for StubAgentBackend."""

    async def test_configure_succeeds(self):
        backend = StubAgentBackend()
        await backend.configure([], AgentRunConfig())
        assert backend._configured is True

    async def test_execute_yields_custom_events(self):
        custom_events = [
            AgentEvent(event_type="text", data={"text": "hello"}),
            AgentEvent(event_type="result", data={"turns": 1, "cost_usd": 0.0}),
        ]
        backend = StubAgentBackend(events=custom_events)
        await backend.configure([], AgentRunConfig())

        events = []
        async for event in backend.execute("anything"):
            events.append(event)

        assert len(events) == 2
        assert events[0].data["text"] == "hello"

    async def test_execute_with_real_tools(self, lab):
        """When configured with real tool defs, stub calls actual tool handlers."""
        tools = collect_all_tools(lab)
        config = AgentRunConfig(domain_id="test-domain-123")
        backend = StubAgentBackend()
        await backend.configure(tools, config)

        events = []
        async for event in backend.execute("test prompt"):
            events.append(event)

        # Should have tool_call/tool_result pairs plus text and result
        event_types = [e.event_type for e in events]
        assert "tool_call" in event_types
        assert "tool_result" in event_types
        assert event_types[0] == "text"  # Planning announcement
        assert event_types[-1] == "result"  # Final result

        # Should have called: search_knowledge, create_experiment,
        # complete_experiment, log_metrics, write_knowledge
        tool_calls = [e for e in events if e.event_type == "tool_call"]
        tool_names = [e.data["tool"] for e in tool_calls]
        assert "search_knowledge" in tool_names
        assert "create_experiment" in tool_names
        assert "complete_experiment" in tool_names
        assert "log_metrics" in tool_names
        assert "write_knowledge" in tool_names

    async def test_execute_creates_experiment_in_store(self, lab):
        """The scripted flow should actually create an experiment in the store."""
        tools = collect_all_tools(lab)
        config = AgentRunConfig(domain_id="test-domain-456")
        backend = StubAgentBackend()
        await backend.configure(tools, config)

        async for _ in backend.execute("create experiment test"):
            pass

        experiments = await lab.experiment_store.list()
        assert len(experiments) == 1
        exp = experiments[0]
        assert exp.domain_id == "test-domain-456"
        assert exp.result is not None
        assert exp.result.metrics["accuracy"] == pytest.approx(0.95)

    async def test_execute_writes_knowledge(self, lab):
        """The scripted flow should write a knowledge atom."""
        tools = collect_all_tools(lab)
        config = AgentRunConfig(domain_id="test-domain-789")
        backend = StubAgentBackend()
        await backend.configure(tools, config)

        async for _ in backend.execute("knowledge test"):
            pass

        atoms = await lab.memory_store.list()
        assert len(atoms) >= 1
        assert any("95%" in a.claim for a in atoms)

    async def test_execute_logs_metrics_to_tracking(self, lab):
        """The scripted flow should log metrics via the tracking backend."""
        tools = collect_all_tools(lab)
        config = AgentRunConfig(domain_id="test-domain-track")
        backend = StubAgentBackend()
        await backend.configure(tools, config)

        async for _ in backend.execute("tracking test"):
            pass

        experiments = await lab.experiment_store.list()
        assert len(experiments) == 1
        tracked = await lab.tracking.get_metrics(experiments[0].id)
        assert tracked["accuracy"] == pytest.approx(0.95)

    async def test_stop_is_noop(self):
        backend = StubAgentBackend()
        await backend.stop()  # Should not raise

    def test_name_is_stub(self):
        backend = StubAgentBackend()
        assert backend.name == "stub"

    def test_is_agent_backend(self):
        backend = StubAgentBackend()
        assert isinstance(backend, AgentBackend)


class TestAgentBackendFactory:
    """Tests for create_agent_backend factory."""

    def test_create_stub_backend(self):
        backend = create_agent_backend("stub")
        assert isinstance(backend, StubAgentBackend)

    def test_unknown_backend_raises(self):
        with pytest.raises(ValueError, match="Unknown agent backend"):
            create_agent_backend("nonexistent")
