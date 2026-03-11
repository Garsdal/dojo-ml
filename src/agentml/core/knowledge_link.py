"""Knowledge linking models — many-to-many links and version snapshots."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

from agentml.utils.ids import generate_id


class LinkType(StrEnum):
    """Types of relationships between knowledge atoms and experiments."""

    CREATED_BY = "created_by"
    UPDATED_BY = "updated_by"
    SUPPORTED_BY = "supported_by"
    CONTRADICTED_BY = "contradicted_by"


@dataclass
class KnowledgeLink:
    """A link between a knowledge atom and an experiment/domain."""

    id: str = field(default_factory=generate_id)
    atom_id: str = ""
    experiment_id: str = ""
    domain_id: str = ""
    link_type: LinkType = LinkType.CREATED_BY
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class KnowledgeSnapshot:
    """A versioned snapshot of a knowledge atom at a point in time."""

    id: str = field(default_factory=generate_id)
    atom_id: str = ""
    version: int = 1
    confidence: float = 0.0
    claim: str = ""
    evidence_ids: list[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
