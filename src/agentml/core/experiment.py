"""Experiment domain models."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from agentml.core.state_machine import ExperimentState
from agentml.utils.ids import generate_id


@dataclass
class Hypothesis:
    """A hypothesis to be tested by an experiment."""

    description: str
    variables: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExperimentResult:
    """Result of an experiment run."""

    metrics: dict[str, float] = field(default_factory=dict)
    artifacts: list[str] = field(default_factory=list)
    logs: list[str] = field(default_factory=list)
    error: str | None = None


@dataclass
class Experiment:
    """An individual experiment within a domain."""

    id: str = field(default_factory=generate_id)
    domain_id: str = ""
    hypothesis: Hypothesis | None = None
    config: dict[str, Any] = field(default_factory=dict)
    state: ExperimentState = ExperimentState.PENDING
    result: ExperimentResult | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
