"""Stub agent — mock implementation for PoC testing without LLM."""

from __future__ import annotations

from typing import TYPE_CHECKING

from agentml.core.experiment import Experiment, ExperimentResult, Hypothesis
from agentml.core.knowledge import KnowledgeAtom
from agentml.core.state_machine import ExperimentState
from agentml.core.task import TaskResult
from agentml.interfaces.agent import Agent

if TYPE_CHECKING:
    from agentml.core.task import Task
    from agentml.runtime.lab import LabEnvironment


class StubAgent(Agent):
    """A stub agent that creates a mock experiment and returns a result.

    Used for PoC testing — no LLM key required.
    """

    async def run(self, task: Task, lab: LabEnvironment) -> TaskResult:
        """Execute a task with a hardcoded experiment flow."""
        # Create an experiment
        experiment = Experiment(
            task_id=task.id,
            hypothesis=Hypothesis(
                description=f"Stub hypothesis for: {task.prompt}",
                variables={"model": "stub"},
            ),
            config={"type": "stub"},
        )

        # Save it
        await lab.experiment_store.save(experiment)

        # Transition to running
        experiment.state = ExperimentState.RUNNING
        await lab.experiment_store.save(experiment)

        # "Run" the experiment and produce a result
        experiment.result = ExperimentResult(
            metrics={"accuracy": 0.95, "f1_score": 0.93},
            logs=["Stub experiment completed successfully"],
        )
        experiment.state = ExperimentState.COMPLETED
        await lab.experiment_store.save(experiment)

        # Log metrics and params
        await lab.tracking.log_metrics(experiment.id, experiment.result.metrics)
        await lab.tracking.log_params(experiment.id, experiment.config)

        # Write a knowledge atom to the memory store
        atom = KnowledgeAtom(
            context=f"Task: {task.prompt}",
            claim="Stub model achieves 95% accuracy on test data.",
            action="Use stub model as baseline for comparison.",
            confidence=0.85,
            evidence_ids=[experiment.id],
        )
        await lab.memory_store.add(atom)

        return TaskResult(
            summary=f"Stub agent completed task: {task.prompt}",
            best_experiment_id=experiment.id,
            metrics=experiment.result.metrics,
            details={"experiments_run": 1},
        )
