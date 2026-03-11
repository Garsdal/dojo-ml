"""Experiment service — orchestrates experiment lifecycle using LabEnvironment."""

from datetime import UTC, datetime

from agentml.core.experiment import Experiment
from agentml.core.state_machine import ExperimentState, transition
from agentml.runtime.lab import LabEnvironment
from agentml.utils.logging import get_logger

logger = get_logger(__name__)


class ExperimentService:
    """Creates, runs, and records experiments through the LabEnvironment."""

    def __init__(self, lab: LabEnvironment) -> None:
        self.lab = lab

    async def create(self, experiment: Experiment) -> str:
        """Create and persist a new experiment.

        Returns:
            The experiment ID.
        """
        experiment_id = await self.lab.experiment_store.save(experiment)
        logger.info("experiment_created", experiment_id=experiment_id)
        return experiment_id

    async def run(self, experiment_id: str) -> Experiment:
        """Transition an experiment to RUNNING state.

        Returns:
            The updated experiment.

        Raises:
            ValueError: If experiment not found.
        """
        experiment = await self.lab.experiment_store.load(experiment_id)
        if experiment is None:
            raise ValueError(f"Experiment not found: {experiment_id}")

        experiment.state = transition(experiment.state, ExperimentState.RUNNING)
        experiment.updated_at = datetime.now(UTC)
        await self.lab.experiment_store.save(experiment)

        logger.info("experiment_running", experiment_id=experiment_id)
        return experiment

    async def complete(self, experiment: Experiment) -> Experiment:
        """Mark an experiment as completed.

        Returns:
            The updated experiment.
        """
        experiment.state = transition(experiment.state, ExperimentState.COMPLETED)
        experiment.updated_at = datetime.now(UTC)
        await self.lab.experiment_store.save(experiment)

        if experiment.result and experiment.result.metrics:
            await self.lab.tracking.log_metrics(experiment.id, experiment.result.metrics)

        logger.info("experiment_completed", experiment_id=experiment.id)
        return experiment

    async def fail(self, experiment: Experiment, error: str) -> Experiment:
        """Mark an experiment as failed.

        Returns:
            The updated experiment.
        """
        experiment.state = transition(experiment.state, ExperimentState.FAILED)
        experiment.updated_at = datetime.now(UTC)
        if experiment.result:
            experiment.result.error = error
        await self.lab.experiment_store.save(experiment)

        logger.info("experiment_failed", experiment_id=experiment.id, error=error)
        return experiment

    async def get(self, experiment_id: str) -> Experiment | None:
        """Get an experiment by ID."""
        return await self.lab.experiment_store.load(experiment_id)

    async def list(self, *, domain_id: str | None = None) -> list[Experiment]:
        """List experiments, optionally filtered by domain ID."""
        return await self.lab.experiment_store.list(domain_id=domain_id)
