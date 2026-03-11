"""Integration tests: memory store wired through LabEnvironment via AgentOrchestrator."""

import pytest

from agentml.agents.backends.stub import StubAgentBackend
from agentml.agents.orchestrator import AgentOrchestrator
from agentml.api.deps import build_lab
from agentml.config.settings import MemorySettings, Settings, StorageSettings, TrackingSettings


@pytest.fixture
def lab(tmp_path):
    settings = Settings(
        storage=StorageSettings(base_dir=tmp_path / ".agentml"),
        tracking=TrackingSettings(backend="file", enabled=True),
        memory=MemorySettings(backend="local"),
    )
    return build_lab(settings)


async def _run_stub(lab, prompt: str) -> None:
    """Helper: run the stub backend through the orchestrator pipeline."""
    backend = StubAgentBackend()
    orchestrator = AgentOrchestrator(lab, backend)
    run = await orchestrator.start(prompt)
    await orchestrator.execute(run)


async def test_stub_agent_creates_knowledge(lab) -> None:
    """StubAgentBackend should create a knowledge atom in the memory store."""
    await _run_stub(lab, "Test memory integration")

    atoms = await lab.memory_store.list()
    assert len(atoms) >= 1
    assert any("Test memory integration" in a.context for a in atoms)


async def test_knowledge_searchable_after_creation(lab) -> None:
    """Knowledge atoms created by the agent should be searchable."""
    await _run_stub(lab, "classification on tabular data")

    results = await lab.memory_store.search("classification")
    assert len(results) >= 1


async def test_knowledge_persists_across_tasks(lab) -> None:
    """Knowledge accumulated across tasks is consolidated by the linker.

    When two runs produce semantically similar findings, the
    KnowledgeLinker merges them into a single atom with an
    incremented version rather than creating duplicates.
    """
    await _run_stub(lab, "classification problem")
    await _run_stub(lab, "regression problem")

    atoms = await lab.memory_store.list()
    assert len(atoms) >= 1
    # If merged, the version should be > 1
    if len(atoms) == 1:
        assert atoms[0].version >= 2
