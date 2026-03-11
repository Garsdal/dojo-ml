"""Knowledge atom domain model."""

from dataclasses import dataclass, field
from datetime import UTC, datetime

from agentml.utils.ids import generate_id


@dataclass
class KnowledgeAtom:
    """A single unit of knowledge extracted from experiments."""

    id: str = field(default_factory=generate_id)
    context: str = ""
    claim: str = ""
    action: str = ""
    confidence: float = 0.0
    evidence_ids: list[str] = field(default_factory=list)
    version: int = 1
    supersedes: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
