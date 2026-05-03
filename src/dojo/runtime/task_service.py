"""TaskService — manages the Task lifecycle on a Domain."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from dojo.core.task import TASK_TYPE_REGISTRY, Task, TaskType
from dojo.runtime.lab import LabEnvironment
from dojo.utils.logging import get_logger

logger = get_logger(__name__)


class TaskNotReadyError(Exception):
    """Raised when an agent run is attempted against a domain without a frozen task."""


class TaskFrozenError(Exception):
    """Raised when a modification is attempted on a frozen task."""


class TaskVerificationError(Exception):
    """Raised when freezing a task whose required tools haven't been verified.

    Carries `errors` so callers can surface specific failures (e.g.
    "load_data: missing required key 'y_test'").
    """

    def __init__(self, message: str, *, errors: list[str] | None = None) -> None:
        super().__init__(message)
        self.errors = errors or []


class TaskService:
    """Creates, configures, freezes, and retrieves Tasks on Domains."""

    def __init__(self, lab: LabEnvironment) -> None:
        self.lab = lab

    async def create(
        self,
        domain_id: str,
        *,
        task_type: TaskType = TaskType.REGRESSION,
        name: str = "",
        description: str = "",
        config: dict[str, Any] | None = None,
    ) -> Task:
        """Create and attach a Task to a Domain.

        Raises ValueError if the domain already has a task (unfreeze + remove first).
        """
        domain = await self.lab.domain_store.load(domain_id)
        if domain is None:
            raise ValueError(f"Domain {domain_id!r} not found")

        spec = TASK_TYPE_REGISTRY[task_type]
        task_config = {**{k: v for k, v in spec.config_schema.get("optional", {}).items()}}
        # Seed expected_metrics from the evaluator contract — `complete_experiment`
        # validates that recorded metric keys are a subset of these.
        evaluator = next((c for c in spec.required_tools if c.name == "evaluate"), None)
        if evaluator is not None:
            task_config.setdefault("expected_metrics", list(evaluator.returns_schema.keys()))
        if config:
            task_config.update(config)

        task = Task(
            type=task_type,
            name=name or f"{task_type.value} task",
            description=description,
            primary_metric=spec.default_metric,
            direction=spec.default_direction,
            config=task_config,
        )
        domain.task = task
        domain.updated_at = datetime.now(UTC)
        await self.lab.domain_store.save(domain)

        logger.info("task_created", domain_id=domain_id, task_id=task.id, type=task_type)
        return task

    async def get(self, domain_id: str) -> Task | None:
        """Return the Task for a Domain, or None if none is set."""
        domain = await self.lab.domain_store.load(domain_id)
        return domain.task if domain else None

    async def update_config(self, domain_id: str, config_updates: dict[str, Any]) -> Task:
        """Update the task config. Raises TaskFrozenError if the task is frozen."""
        domain = await self.lab.domain_store.load(domain_id)
        if domain is None:
            raise ValueError(f"Domain {domain_id!r} not found")
        if domain.task is None:
            raise ValueError(f"Domain {domain_id!r} has no task")
        if domain.task.frozen:
            raise TaskFrozenError("Cannot update config on a frozen task — unfreeze first")

        domain.task.config.update(config_updates)
        domain.task.updated_at = datetime.now(UTC)
        domain.updated_at = datetime.now(UTC)
        await self.lab.domain_store.save(domain)
        return domain.task

    async def freeze(self, domain_id: str, *, skip_verification: bool = False) -> Task:
        """Freeze the task so agent runs are permitted.

        Every required tool (per `TASK_TYPE_REGISTRY`) must be present *and*
        have `verification.verified is True`. Pass ``skip_verification=True``
        only for explicit user overrides (e.g. CLI ``--unsafe-skip-verify``).
        """
        domain = await self.lab.domain_store.load(domain_id)
        if domain is None:
            raise ValueError(f"Domain {domain_id!r} not found")
        if domain.task is None:
            raise ValueError(f"Domain {domain_id!r} has no task — create one first")

        if not skip_verification:
            errors = _verification_errors(domain.task)
            if errors:
                raise TaskVerificationError(
                    "Task cannot be frozen — verification gate failed.",
                    errors=errors,
                )

        domain.task.frozen = True
        domain.task.updated_at = datetime.now(UTC)
        domain.updated_at = datetime.now(UTC)
        await self.lab.domain_store.save(domain)

        logger.info("task_frozen", domain_id=domain_id, task_id=domain.task.id)
        return domain.task

    async def unfreeze(self, domain_id: str) -> Task:
        """Unfreeze the task to allow tool changes.

        Note: unfreezing invalidates metric comparisons across experiments
        if tool code changes — callers should surface this warning.
        """
        domain = await self.lab.domain_store.load(domain_id)
        if domain is None:
            raise ValueError(f"Domain {domain_id!r} not found")
        if domain.task is None:
            raise ValueError(f"Domain {domain_id!r} has no task")

        domain.task.frozen = False
        domain.task.updated_at = datetime.now(UTC)
        domain.updated_at = datetime.now(UTC)
        await self.lab.domain_store.save(domain)

        logger.info("task_unfrozen", domain_id=domain_id, task_id=domain.task.id)
        return domain.task

    async def delete(self, domain_id: str) -> None:
        """Remove the task from a domain (only allowed if not frozen)."""
        domain = await self.lab.domain_store.load(domain_id)
        if domain is None:
            raise ValueError(f"Domain {domain_id!r} not found")
        if domain.task and domain.task.frozen:
            raise TaskFrozenError("Cannot delete a frozen task — unfreeze first")

        domain.task = None
        domain.updated_at = datetime.now(UTC)
        await self.lab.domain_store.save(domain)

    def assert_ready(self, domain_id: str, task: Task | None) -> None:
        """Raise TaskNotReadyError if the task is missing, unfrozen, or has
        unverified required tools.

        Called by the orchestrator before starting a run.
        """
        if task is None:
            raise TaskNotReadyError(
                f"Domain {domain_id!r} has no task. "
                "Create one with `dojo task create` or POST /domains/{id}/task."
            )
        if not task.frozen:
            raise TaskNotReadyError(
                f"Domain {domain_id!r} task is not frozen. "
                "Freeze it with `dojo task freeze` or POST /domains/{id}/task/freeze."
            )
        errors = _verification_errors(task)
        if errors:
            raise TaskNotReadyError(
                f"Domain {domain_id!r} has unverified tools: " + "; ".join(errors)
            )


def _verification_errors(task: Task) -> list[str]:
    """Return human-readable problems with the task's required tool verifications.

    Empty list means the task is ready to freeze / run.
    """
    spec = TASK_TYPE_REGISTRY.get(task.type)
    if spec is None:
        return []

    by_name = {t.name: t for t in task.tools}
    out: list[str] = []
    for contract in spec.required_tools:
        tool = by_name.get(contract.name)
        if tool is None:
            out.append(f"required tool {contract.name!r} is missing")
            continue
        if tool.verification is None:
            out.append(f"{contract.name}: not yet verified — run `dojo task generate`")
            continue
        if not tool.verification.verified:
            details = "; ".join(tool.verification.errors) or "verification failed"
            out.append(f"{contract.name}: {details}")
    return out
