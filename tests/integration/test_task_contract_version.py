"""contract_version: stale frozen tasks must re-verify before agent runs."""

from __future__ import annotations

from pathlib import Path

import pytest

from dojo.core.domain import Domain, DomainTool, Workspace, WorkspaceSource
from dojo.core.task import TASK_TYPE_REGISTRY, TaskType
from dojo.runtime.task_service import TaskNotReadyError, TaskService


def _domain(tmp_path: Path, name: str = "t") -> Domain:
    return Domain(
        name=name,
        prompt="t",
        workspace=Workspace(
            source=WorkspaceSource.LOCAL,
            path=str(tmp_path / "ws"),
            ready=True,
        ),
    )


async def test_freeze_stamps_contract_version_on_task(lab, tmp_path):
    domain = _domain(tmp_path)
    Path(domain.workspace.path).mkdir(parents=True, exist_ok=True)
    await lab.domain_store.save(domain)

    service = TaskService(lab)
    await service.create(domain.id, task_type=TaskType.REGRESSION)
    domain = await lab.domain_store.load(domain.id)
    domain.task.tools = [
        DomainTool(name="load_data", module_filename="load_data.py", code="x"),
        DomainTool(name="evaluate", module_filename="evaluate.py", code="x"),
    ]
    await lab.domain_store.save(domain)
    await service.freeze(domain.id, skip_verification=True)

    domain = await lab.domain_store.load(domain.id)
    spec = TASK_TYPE_REGISTRY[TaskType.REGRESSION]
    assert domain.task.config.get("contract_version") == spec.contract_version


async def test_assert_ready_rejects_stale_contract_version(lab, tmp_path):
    domain = _domain(tmp_path)
    Path(domain.workspace.path).mkdir(parents=True, exist_ok=True)
    await lab.domain_store.save(domain)

    service = TaskService(lab)
    await service.create(domain.id, task_type=TaskType.REGRESSION)
    domain = await lab.domain_store.load(domain.id)
    domain.task.tools = [
        DomainTool(name="load_data", module_filename="load_data.py", code="x"),
        DomainTool(name="evaluate", module_filename="evaluate.py", code="x"),
    ]
    await lab.domain_store.save(domain)
    await service.freeze(domain.id, skip_verification=True)

    domain = await lab.domain_store.load(domain.id)
    domain.task.config["contract_version"] = 0
    await lab.domain_store.save(domain)

    with pytest.raises(TaskNotReadyError, match="contract version"):
        service.assert_ready(domain.id, domain.task)


async def test_assert_ready_treats_missing_contract_version_as_stale(lab, tmp_path):
    domain = _domain(tmp_path)
    Path(domain.workspace.path).mkdir(parents=True, exist_ok=True)
    await lab.domain_store.save(domain)

    service = TaskService(lab)
    await service.create(domain.id, task_type=TaskType.REGRESSION)
    domain = await lab.domain_store.load(domain.id)
    domain.task.tools = [
        DomainTool(name="load_data", module_filename="load_data.py", code="x"),
        DomainTool(name="evaluate", module_filename="evaluate.py", code="x"),
    ]
    await lab.domain_store.save(domain)
    await service.freeze(domain.id, skip_verification=True)

    domain = await lab.domain_store.load(domain.id)
    domain.task.config.pop("contract_version", None)
    await lab.domain_store.save(domain)

    with pytest.raises(TaskNotReadyError, match="contract version"):
        service.assert_ready(domain.id, domain.task)
