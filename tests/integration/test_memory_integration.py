"""Integration tests: memory store wired through LabEnvironment."""

import pytest

from agentml.agents.stub_agent import StubAgent
from agentml.api.deps import build_lab
from agentml.config.settings import MemorySettings, Settings, StorageSettings, TrackingSettings
from agentml.core.task import Task


@pytest.fixture
def lab(tmp_path):
    settings = Settings(
        storage=StorageSettings(base_dir=tmp_path / ".agentml"),
        tracking=TrackingSettings(backend="file", enabled=True),
        memory=MemorySettings(backend="local"),
    )
    return build_lab(settings)


async def test_stub_agent_creates_knowledge(lab) -> None:
    """StubAgent should create a knowledge atom in the memory store."""
    task = Task(prompt="Test memory integration")
    agent = StubAgent()
    await agent.run(task, lab)

    atoms = await lab.memory_store.list()
    assert len(atoms) >= 1
    assert any("Test memory integration" in a.context for a in atoms)


async def test_knowledge_searchable_after_creation(lab) -> None:
    """Knowledge atoms created by the agent should be searchable."""
    task = Task(prompt="classification on tabular data")
    agent = StubAgent()
    await agent.run(task, lab)

    results = await lab.memory_store.search("classification")
    assert len(results) >= 1


async def test_knowledge_persists_across_tasks(lab) -> None:
    """Knowledge accumulated across tasks should all be available."""
    agent = StubAgent()
    await agent.run(Task(prompt="classification problem"), lab)
    await agent.run(Task(prompt="regression problem"), lab)

    atoms = await lab.memory_store.list()
    assert len(atoms) >= 2
