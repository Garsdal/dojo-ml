"""Unit tests for AgentBackend, StubAgentBackend, and factory."""

import pytest

from dojo.agents.backend import AgentBackend
from dojo.agents.backends.stub import StubAgentBackend
from dojo.agents.factory import create_agent_backend
from dojo.agents.types import AgentEvent, AgentRunConfig
from dojo.tools.server import collect_all_tools


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
        """Phase 4: stub emits the new two-tool flow even without a frozen domain.

        run_experiment returns an error result (no frozen task), but the stub
        keeps going so callers still see the full event sequence.
        """
        tools = collect_all_tools(lab)
        config = AgentRunConfig(domain_id="test-domain-123")
        backend = StubAgentBackend()
        await backend.configure(tools, config)

        events = []
        async for event in backend.execute("test prompt"):
            events.append(event)

        event_types = [e.event_type for e in events]
        assert event_types[0] == "text"  # Planning announcement
        assert event_types[-1] == "result"  # Final result
        assert "tool_call" in event_types
        assert "tool_result" in event_types

        tool_calls = [e for e in events if e.event_type == "tool_call"]
        tool_names = [e.data["tool"] for e in tool_calls]
        assert "search_knowledge" in tool_names
        assert "run_experiment" in tool_names
        assert "write_knowledge" in tool_names

    async def test_execute_writes_knowledge_even_without_frozen_domain(self, lab):
        """write_knowledge is global — works without a domain. The stub flow
        guarantees a knowledge atom regardless of whether run_experiment ran."""
        tools = collect_all_tools(lab)
        config = AgentRunConfig(domain_id="test-domain-789")
        backend = StubAgentBackend()
        await backend.configure(tools, config)

        async for _ in backend.execute("knowledge test"):
            pass

        atoms = await lab.memory_store.list()
        assert len(atoms) >= 1
        assert any("baseline" in a.claim.lower() for a in atoms)

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
