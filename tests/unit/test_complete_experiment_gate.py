"""Phase 3: complete_experiment rejects metric keys outside the task contract."""

from __future__ import annotations

import pytest

from dojo.core.domain import Domain
from dojo.core.experiment import Experiment, Hypothesis
from dojo.core.task import TaskType
from dojo.runtime.task_service import TaskService
from dojo.tools.experiments import create_experiment_tools


@pytest.fixture
async def domain_with_task(lab) -> Domain:
    domain = Domain(name="contract")
    await lab.domain_store.save(domain)
    await TaskService(lab).create(domain.id, task_type=TaskType.REGRESSION)
    return await lab.domain_store.load(domain.id)


async def _create_experiment(lab, domain_id: str) -> str:
    exp = Experiment(domain_id=domain_id, hypothesis=Hypothesis(description="h"))
    eid = await lab.experiment_store.save(exp)
    return eid


async def test_complete_experiment_accepts_contract_metrics(lab, domain_with_task):
    tools = {t.name: t for t in create_experiment_tools(lab)}

    create = await tools["create_experiment"].handler(
        {"domain_id": domain_with_task.id, "hypothesis": "h"}
    )
    eid = create.data["experiment_id"]

    result = await tools["complete_experiment"].handler(
        {
            "experiment_id": eid,
            "metrics": {"rmse": 1.2, "r2": 0.9, "mae": 0.4},
        }
    )
    assert result.error is None
    assert result.data["metrics"]["rmse"] == 1.2


async def test_complete_experiment_rejects_extra_metric_keys(lab, domain_with_task):
    tools = {t.name: t for t in create_experiment_tools(lab)}

    create = await tools["create_experiment"].handler(
        {"domain_id": domain_with_task.id, "hypothesis": "h"}
    )
    eid = create.data["experiment_id"]

    # Inject a bogus metric not in the contract
    result = await tools["complete_experiment"].handler(
        {
            "experiment_id": eid,
            "metrics": {"rmse": 1.2, "my_secret_metric": 999.0},
        }
    )
    assert result.error is not None
    assert "my_secret_metric" in result.error
    assert "evaluate" in result.error


async def test_complete_experiment_passes_when_no_task(lab):
    """Domains without a task fall through — no contract to enforce."""
    from dojo.core.domain import Domain

    domain = Domain(name="no-task")
    await lab.domain_store.save(domain)
    tools = {t.name: t for t in create_experiment_tools(lab)}

    create = await tools["create_experiment"].handler({"domain_id": domain.id, "hypothesis": "h"})
    eid = create.data["experiment_id"]

    result = await tools["complete_experiment"].handler(
        {"experiment_id": eid, "metrics": {"anything_goes": 42.0}}
    )
    assert result.error is None
