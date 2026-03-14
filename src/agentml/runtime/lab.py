"""Lab environment — dependency injection container for all backends."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from agentml.interfaces.artifact_store import ArtifactStore
from agentml.interfaces.compute import ComputeBackend
from agentml.interfaces.domain_store import DomainStore
from agentml.interfaces.experiment_store import ExperimentStore
from agentml.interfaces.knowledge_link_store import KnowledgeLinkStore
from agentml.interfaces.knowledge_linker import KnowledgeLinker
from agentml.interfaces.memory_store import MemoryStore
from agentml.interfaces.sandbox import Sandbox
from agentml.interfaces.tracking import TrackingConnector


@dataclass
class LabEnvironment:
    """Holds all injected backends — the DI container for AgentML."""

    compute: ComputeBackend
    sandbox: Sandbox
    experiment_store: ExperimentStore
    artifact_store: ArtifactStore
    memory_store: MemoryStore
    tracking: TrackingConnector
    domain_store: DomainStore
    knowledge_link_store: KnowledgeLinkStore
    knowledge_linker: KnowledgeLinker
    settings: Any | None = field(default=None)
