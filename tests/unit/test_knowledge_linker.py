"""Unit tests for KnowledgeLinker — the knowledge compression/linking service."""

from pathlib import Path

import pytest

from agentml.runtime.knowledge_linker import KnowledgeLinker
from agentml.storage.local_knowledge_link import LocalKnowledgeLinkStore
from agentml.storage.local_memory import LocalMemoryStore


@pytest.fixture
def memory_store(tmp_dir: Path):
    return LocalMemoryStore(base_dir=tmp_dir / "memory")


@pytest.fixture
def link_store(tmp_dir: Path):
    return LocalKnowledgeLinkStore(base_dir=tmp_dir / "knowledge_links")


@pytest.fixture
def linker(memory_store, link_store):
    return KnowledgeLinker(memory_store, link_store)


async def test_produce_creates_new_atom(linker: KnowledgeLinker, memory_store):
    result = await linker.produce_knowledge(
        context="Housing price prediction experiment",
        claim="Random forests outperform linear regression on tabular housing data",
        confidence=0.85,
        experiment_id="exp-001",
        domain_id="domain-001",
    )

    assert result.action == "created"
    assert result.version == 1
    assert result.confidence == 0.85
    assert result.merged_with is None

    # Atom should exist in memory store
    atoms = await memory_store.list()
    assert len(atoms) == 1
    assert atoms[0].id == result.atom_id


async def test_produce_merges_similar_atoms(linker: KnowledgeLinker, memory_store):
    # Create an initial atom
    await linker.produce_knowledge(
        context="Housing price prediction experiment with gradient boosting",
        claim="Random forests outperform linear regression on tabular housing data",
        confidence=0.8,
        experiment_id="exp-001",
        domain_id="domain-001",
    )

    # Produce a similar finding — should merge
    result = await linker.produce_knowledge(
        context="Extended housing price prediction experiment with cross-validation",
        claim="Random forests outperform linear regression on tabular housing data significantly",
        confidence=0.9,
        experiment_id="exp-002",
        domain_id="domain-001",
    )

    assert result.action == "merged"
    assert result.version == 2
    # Merged confidence is avg of old (0.8) and new (0.9) = 0.85
    assert result.confidence == pytest.approx(0.85)

    # Only one atom in store (merged)
    atoms = await memory_store.list()
    assert len(atoms) == 1


async def test_produce_distinct_atoms_not_merged(linker: KnowledgeLinker, memory_store):
    await linker.produce_knowledge(
        context="Image classification with convolutional neural networks",
        claim="CNNs achieve 95% accuracy on CIFAR-10 with data augmentation enabled",
        confidence=0.9,
        experiment_id="exp-001",
        domain_id="domain-001",
    )

    await linker.produce_knowledge(
        context="Natural language processing with transformers",
        claim="BERT fine-tuning achieves state-of-the-art on sentiment analysis benchmarks",
        confidence=0.85,
        experiment_id="exp-002",
        domain_id="domain-001",
    )

    atoms = await memory_store.list()
    assert len(atoms) == 2


async def test_links_created_for_new_atom(linker: KnowledgeLinker, link_store):
    result = await linker.produce_knowledge(
        context="Testing link creation for classification experiments",
        claim="Gradient boosting consistently outperforms decision trees on structured data",
        experiment_id="exp-001",
        domain_id="domain-001",
    )

    links = await link_store.get_links_for_atom(result.atom_id)
    assert len(links) == 1
    assert links[0].experiment_id == "exp-001"
    assert links[0].domain_id == "domain-001"
    assert links[0].link_type == "created_by"


async def test_snapshot_created_on_produce(linker: KnowledgeLinker, link_store):
    result = await linker.produce_knowledge(
        context="Snapshot creation test for experimental results tracking",
        claim="XGBoost with tuned hyperparameters beats default random forest configuration",
        confidence=0.7,
        experiment_id="exp-001",
        domain_id="domain-001",
    )

    snapshots = await link_store.get_snapshots(result.atom_id)
    assert len(snapshots) == 1
    assert snapshots[0].version == 1
    assert snapshots[0].confidence == pytest.approx(0.7)


async def test_get_domain_knowledge(linker: KnowledgeLinker):
    await linker.produce_knowledge(
        context="Domain knowledge retrieval test with image experiments",
        claim="CNNs require significant GPU memory for large batch training sizes",
        domain_id="domain-001",
    )
    await linker.produce_knowledge(
        context="Separate domain test for text classification comparison",
        claim="BERT models need extensive fine-tuning on small labeled text datasets",
        domain_id="domain-002",
    )

    d1_atoms = await linker.get_domain_knowledge("domain-001")
    assert len(d1_atoms) == 1

    d2_atoms = await linker.get_domain_knowledge("domain-002")
    assert len(d2_atoms) == 1


async def test_get_evolution(linker: KnowledgeLinker):
    await linker.produce_knowledge(
        context="Evolution tracking test with gradient boosting experiments",
        claim="XGBoost with tuned learning rate of 0.01 outperforms default random forest model",
        confidence=0.6,
        experiment_id="exp-001",
        domain_id="domain-001",
    )
    await linker.produce_knowledge(
        context="Evolution tracking continued with additional gradient boosting experiments",
        claim="XGBoost with tuned learning rate of 0.01 outperforms default random forest model significantly",
        confidence=0.9,
        experiment_id="exp-002",
        domain_id="domain-001",
    )

    snapshots = await linker.get_evolution("domain-001")
    assert len(snapshots) >= 2
    # Snapshots should be sorted by timestamp
    for i in range(len(snapshots) - 1):
        assert snapshots[i].timestamp <= snapshots[i + 1].timestamp


async def test_get_atom_history(linker: KnowledgeLinker, memory_store):
    # Create and then merge to get version history
    result1 = await linker.produce_knowledge(
        context="Version history test with neural network architecture search",
        claim="ResNet-50 achieves 92% accuracy on custom image classification dataset",
        confidence=0.7,
        experiment_id="exp-001",
        domain_id="domain-001",
    )
    await linker.produce_knowledge(
        context="Version history continued with advanced neural network architecture search",
        claim="ResNet-50 achieves 92% accuracy on custom image classification dataset with dropout",
        confidence=0.85,
        experiment_id="exp-002",
        domain_id="domain-001",
    )

    history = await linker.get_atom_history(result1.atom_id)
    assert len(history) == 2
    assert history[0].version == 1
    assert history[1].version == 2
