"""Tests for ExperimentService."""

import pytest

from agentml.core.experiment import Experiment, ExperimentResult
from agentml.core.state_machine import ExperimentState
from agentml.runtime.experiment_service import ExperimentService
from agentml.runtime.lab import LabEnvironment


@pytest.fixture
def service(lab: LabEnvironment) -> ExperimentService:
    return ExperimentService(lab)


async def test_create_experiment(service: ExperimentService):
    exp = Experiment(domain_id="domain-1")
    exp_id = await service.create(exp)
    assert exp_id == exp.id

    loaded = await service.get(exp_id)
    assert loaded is not None
    assert loaded.domain_id == "domain-1"
    assert loaded.state == ExperimentState.PENDING


async def test_run_experiment(service: ExperimentService):
    exp = Experiment(domain_id="domain-1")
    await service.create(exp)

    running = await service.run(exp.id)
    assert running.state == ExperimentState.RUNNING


async def test_complete_experiment(service: ExperimentService):
    exp = Experiment(domain_id="domain-1")
    await service.create(exp)
    exp = await service.run(exp.id)

    exp.result = ExperimentResult(metrics={"accuracy": 0.9})
    completed = await service.complete(exp)
    assert completed.state == ExperimentState.COMPLETED


async def test_fail_experiment(service: ExperimentService):
    exp = Experiment(domain_id="domain-1")
    await service.create(exp)
    exp = await service.run(exp.id)

    failed = await service.fail(exp, error="Something went wrong")
    assert failed.state == ExperimentState.FAILED


async def test_run_nonexistent_raises(service: ExperimentService):
    with pytest.raises(ValueError, match="not found"):
        await service.run("nonexistent-id")


async def test_list_experiments(service: ExperimentService):
    await service.create(Experiment(domain_id="domain-1"))
    await service.create(Experiment(domain_id="domain-1"))
    await service.create(Experiment(domain_id="domain-2"))

    all_exps = await service.list()
    assert len(all_exps) == 3

    domain1_exps = await service.list(domain_id="domain-1")
    assert len(domain1_exps) == 2
