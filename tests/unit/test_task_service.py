"""Unit tests for TaskService — task lifecycle on a Domain."""

import pytest

from dojo.core.domain import DomainTool, ToolType, VerificationResult
from dojo.core.task import TaskType
from dojo.runtime.task_service import (
    TaskFrozenError,
    TaskNotReadyError,
    TaskService,
    TaskVerificationError,
)


def _verified_tool(name: str) -> DomainTool:
    return DomainTool(
        name=name,
        description=f"{name} tool",
        type=ToolType.DATA_LOADER if name == "load_data" else ToolType.EVALUATOR,
        executable=True,
        code="print('ok')",
        verification=VerificationResult(verified=True),
    )


async def test_create_task(lab) -> None:
    from dojo.core.domain import Domain

    domain = Domain(name="test")
    await lab.domain_store.save(domain)

    svc = TaskService(lab)
    task = await svc.create(domain.id, task_type=TaskType.REGRESSION, name="my task")

    assert task.type == TaskType.REGRESSION
    assert task.name == "my task"
    assert task.primary_metric == "rmse"
    assert task.frozen is False


async def test_create_task_sets_default_config(lab) -> None:
    from dojo.core.domain import Domain

    domain = Domain(name="test")
    await lab.domain_store.save(domain)

    svc = TaskService(lab)
    task = await svc.create(domain.id, config={"data_path": "data.csv", "target_column": "y"})

    assert task.config["data_path"] == "data.csv"
    assert task.config["target_column"] == "y"
    assert "test_split_ratio" in task.config  # default from registry


async def test_get_task(lab) -> None:
    from dojo.core.domain import Domain

    domain = Domain(name="test")
    await lab.domain_store.save(domain)
    svc = TaskService(lab)
    await svc.create(domain.id)

    task = await svc.get(domain.id)
    assert task is not None
    assert task.type == TaskType.REGRESSION


async def test_get_task_no_task(lab) -> None:
    from dojo.core.domain import Domain

    domain = Domain(name="test")
    await lab.domain_store.save(domain)

    task = await TaskService(lab).get(domain.id)
    assert task is None


async def test_freeze_and_unfreeze(lab) -> None:
    from dojo.core.domain import Domain

    domain = Domain(name="test")
    await lab.domain_store.save(domain)
    svc = TaskService(lab)
    await svc.create(domain.id)

    frozen = await svc.freeze(domain.id, skip_verification=True)
    assert frozen.frozen is True

    unfrozen = await svc.unfreeze(domain.id)
    assert unfrozen.frozen is False


async def test_update_config_blocked_when_frozen(lab) -> None:
    from dojo.core.domain import Domain

    domain = Domain(name="test")
    await lab.domain_store.save(domain)
    svc = TaskService(lab)
    await svc.create(domain.id)
    await svc.freeze(domain.id, skip_verification=True)

    with pytest.raises(TaskFrozenError):
        await svc.update_config(domain.id, {"data_path": "new.csv"})


async def test_assert_ready_missing_task(lab) -> None:
    svc = TaskService(lab)
    with pytest.raises(TaskNotReadyError, match="has no task"):
        svc.assert_ready("d1", None)


async def test_assert_ready_unfrozen_task(lab) -> None:
    from dojo.core.domain import Domain

    domain = Domain(name="test")
    await lab.domain_store.save(domain)
    svc = TaskService(lab)
    task = await svc.create(domain.id)

    with pytest.raises(TaskNotReadyError, match="not frozen"):
        svc.assert_ready(domain.id, task)


async def test_task_persists_across_load(lab) -> None:
    from dojo.core.domain import Domain

    domain = Domain(name="test")
    await lab.domain_store.save(domain)
    svc = TaskService(lab)
    task = await svc.create(domain.id, config={"data_path": "x.csv", "target_column": "y"})
    await svc.freeze(domain.id, skip_verification=True)

    reloaded = await lab.domain_store.load(domain.id)
    assert reloaded is not None
    assert reloaded.task is not None
    assert reloaded.task.id == task.id
    assert reloaded.task.frozen is True
    assert reloaded.task.config["data_path"] == "x.csv"


async def test_delete_task(lab) -> None:
    from dojo.core.domain import Domain

    domain = Domain(name="test")
    await lab.domain_store.save(domain)
    svc = TaskService(lab)
    await svc.create(domain.id)
    await svc.delete(domain.id)

    assert await svc.get(domain.id) is None


async def test_freeze_blocks_when_required_tools_unverified(lab) -> None:
    from dojo.core.domain import Domain

    domain = Domain(name="test")
    await lab.domain_store.save(domain)
    svc = TaskService(lab)
    await svc.create(domain.id, config={"data_path": "x.csv", "target_column": "y"})

    with pytest.raises(TaskVerificationError) as ei:
        await svc.freeze(domain.id)
    assert any("load_data" in e for e in ei.value.errors)
    assert any("evaluate" in e for e in ei.value.errors)


async def test_freeze_blocks_when_only_one_tool_unverified(lab) -> None:
    from dojo.core.domain import Domain

    domain = Domain(name="test")
    await lab.domain_store.save(domain)
    svc = TaskService(lab)
    await svc.create(domain.id)

    # Only load_data is verified; evaluate is unverified
    domain = await lab.domain_store.load(domain.id)
    domain.task.tools = [_verified_tool("load_data")]
    await lab.domain_store.save(domain)

    with pytest.raises(TaskVerificationError) as ei:
        await svc.freeze(domain.id)
    assert any("evaluate" in e for e in ei.value.errors)


async def test_freeze_succeeds_when_all_required_tools_verified(lab) -> None:
    from dojo.core.domain import Domain

    domain = Domain(name="test")
    await lab.domain_store.save(domain)
    svc = TaskService(lab)
    await svc.create(domain.id)

    domain = await lab.domain_store.load(domain.id)
    domain.task.tools = [_verified_tool("load_data"), _verified_tool("evaluate")]
    await lab.domain_store.save(domain)

    frozen = await svc.freeze(domain.id)
    assert frozen.frozen is True


async def test_assert_ready_unverified_tools(lab) -> None:
    from dojo.core.domain import Domain

    domain = Domain(name="test")
    await lab.domain_store.save(domain)
    svc = TaskService(lab)
    task = await svc.create(domain.id)
    task.frozen = True  # Pretend it was force-frozen

    with pytest.raises(TaskNotReadyError, match="unverified"):
        svc.assert_ready(domain.id, task)


async def test_create_task_seeds_expected_metrics(lab) -> None:
    from dojo.core.domain import Domain

    domain = Domain(name="test")
    await lab.domain_store.save(domain)
    svc = TaskService(lab)
    task = await svc.create(domain.id)
    assert "expected_metrics" in task.config
    assert set(task.config["expected_metrics"]) == {"rmse", "r2", "mae"}


async def test_delete_frozen_task_raises(lab) -> None:
    from dojo.core.domain import Domain

    domain = Domain(name="test")
    await lab.domain_store.save(domain)
    svc = TaskService(lab)
    await svc.create(domain.id)
    await svc.freeze(domain.id, skip_verification=True)

    with pytest.raises(TaskFrozenError):
        await svc.delete(domain.id)
