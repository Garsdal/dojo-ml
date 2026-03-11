"""Tests for local storage implementations."""

from pathlib import Path

import pytest

from agentml.core.experiment import Experiment, ExperimentResult, Hypothesis
from agentml.core.knowledge import KnowledgeAtom
from agentml.core.state_machine import ExperimentState
from agentml.storage.local_artifact import LocalArtifactStore
from agentml.storage.local_experiment import LocalExperimentStore
from agentml.storage.local_memory import LocalMemoryStore


@pytest.fixture
def exp_store(tmp_dir: Path):
    return LocalExperimentStore(base_dir=tmp_dir / "experiments")


@pytest.fixture
def artifact_store(tmp_dir: Path):
    return LocalArtifactStore(base_dir=tmp_dir / "artifacts")


@pytest.fixture
def memory_store(tmp_dir: Path):
    return LocalMemoryStore(base_dir=tmp_dir / "memory")


# --- Experiment Store ---


async def test_experiment_save_load(exp_store: LocalExperimentStore):
    exp = Experiment(
        domain_id="d1",
        hypothesis=Hypothesis(description="Test hyp", variables={"x": 1}),
        config={"model": "test"},
        state=ExperimentState.COMPLETED,
        result=ExperimentResult(metrics={"acc": 0.95}),
    )
    await exp_store.save(exp)
    loaded = await exp_store.load(exp.id)

    assert loaded is not None
    assert loaded.id == exp.id
    assert loaded.domain_id == "d1"
    assert loaded.state == ExperimentState.COMPLETED
    assert loaded.hypothesis is not None
    assert loaded.hypothesis.description == "Test hyp"
    assert loaded.result is not None
    assert loaded.result.metrics["acc"] == 0.95


async def test_experiment_list(exp_store: LocalExperimentStore):
    await exp_store.save(Experiment(domain_id="d1"))
    await exp_store.save(Experiment(domain_id="d2"))

    all_exps = await exp_store.list()
    assert len(all_exps) == 2

    d1_exps = await exp_store.list(domain_id="d1")
    assert len(d1_exps) == 1


async def test_experiment_delete(exp_store: LocalExperimentStore):
    exp = Experiment(domain_id="d1")
    await exp_store.save(exp)

    assert await exp_store.delete(exp.id) is True
    assert await exp_store.load(exp.id) is None
    assert await exp_store.delete(exp.id) is False


async def test_experiment_load_nonexistent(exp_store: LocalExperimentStore):
    assert await exp_store.load("nonexistent") is None


# --- Artifact Store ---


async def test_artifact_save_load(artifact_store: LocalArtifactStore):
    data = b"hello world"
    path = await artifact_store.save("test.bin", data)
    assert path

    loaded = await artifact_store.load("test.bin")
    assert loaded == data


async def test_artifact_list(artifact_store: LocalArtifactStore):
    await artifact_store.save("a.txt", b"a")
    await artifact_store.save("b.txt", b"b")

    artifacts = await artifact_store.list()
    assert len(artifacts) == 2


async def test_artifact_delete(artifact_store: LocalArtifactStore):
    await artifact_store.save("test.bin", b"data")
    assert await artifact_store.delete("test.bin") is True
    assert await artifact_store.load("test.bin") is None


# --- Memory Store ---


async def test_memory_add_search(memory_store: LocalMemoryStore):
    atom = KnowledgeAtom(
        context="machine learning",
        claim="Random forests outperform logistic regression on tabular data",
        action="Use random forest as baseline",
        confidence=0.8,
    )
    await memory_store.add(atom)

    results = await memory_store.search("random forest")
    assert len(results) == 1
    assert results[0].id == atom.id


async def test_memory_list(memory_store: LocalMemoryStore):
    await memory_store.add(KnowledgeAtom(claim="A"))
    await memory_store.add(KnowledgeAtom(claim="B"))

    atoms = await memory_store.list()
    assert len(atoms) == 2


async def test_memory_delete(memory_store: LocalMemoryStore):
    atom = KnowledgeAtom(claim="test")
    await memory_store.add(atom)

    assert await memory_store.delete(atom.id) is True
    atoms = await memory_store.list()
    assert len(atoms) == 0
