"""Knowledge linking models — links between knowledge atoms and experiments."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

from agentml.utils.ids import generate_id


class LinkType(StrEnum):
    """Types of relationships between knowledge atoms and experiments."""

    CREATED_BY = "created_by"
    RELATED_TO = "related_to"


@dataclass
class KnowledgeLink:
    """A link between a knowledge atom and an experiment/domain."""

    id: str = field(default_factory=generate_id)
    atom_id: str = ""
    experiment_id: str = ""
    domain_id: str = ""
    link_type: LinkType = LinkType.CREATED_BY
    related_atom_id: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
