"""Experiment state machine with valid transitions."""

from enum import StrEnum


class ExperimentState(StrEnum):
    """States an experiment can be in."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    ARCHIVED = "archived"


VALID_TRANSITIONS: dict[ExperimentState, set[ExperimentState]] = {
    ExperimentState.PENDING: {ExperimentState.RUNNING},
    ExperimentState.RUNNING: {ExperimentState.COMPLETED, ExperimentState.FAILED},
    ExperimentState.COMPLETED: {ExperimentState.ARCHIVED},
    ExperimentState.FAILED: {ExperimentState.ARCHIVED},
    ExperimentState.ARCHIVED: set(),
}


class InvalidTransitionError(Exception):
    """Raised when an invalid state transition is attempted."""


def transition(current: ExperimentState, target: ExperimentState) -> ExperimentState:
    """Transition from current state to target state.

    Raises InvalidTransitionError if the transition is not valid.
    """
    if target not in VALID_TRANSITIONS.get(current, set()):
        raise InvalidTransitionError(f"Cannot transition from {current.value} to {target.value}")
    return target
