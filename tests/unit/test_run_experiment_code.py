"""Tests for run_experiment_code tool."""

import pytest

from dojo.core.experiment import Experiment, Hypothesis
from dojo.runtime.experiment_service import ExperimentService
from dojo.tools.experiments import create_experiment_tools


@pytest.fixture
async def running_experiment(lab):
    """Create an experiment in RUNNING state."""
    service = ExperimentService(lab)
    exp = Experiment(
        domain_id="test-domain",
        hypothesis=Hypothesis(description="Test run_experiment_code"),
    )
    exp_id = await service.create(exp)
    await service.run(exp_id)
    return exp_id


async def test_run_experiment_code_success(lab, running_experiment):
    """run_experiment_code executes code and returns stdout."""
    tools = {t.name: t for t in create_experiment_tools(lab)}
    tool = tools["run_experiment_code"]

    result = await tool.handler(
        {
            "experiment_id": running_experiment,
            "code": "print('hello from run_experiment_code')",
            "description": "Basic print test",
        }
    )

    assert result.error is None
    assert result.data["exit_code"] == 0
    assert "hello from run_experiment_code" in result.data["stdout"]
    assert result.data["run_number"] == 1


async def test_run_experiment_code_stores_artifact(lab, running_experiment):
    """run_experiment_code stores the code as an artifact."""
    tools = {t.name: t for t in create_experiment_tools(lab)}
    tool = tools["run_experiment_code"]

    code = "x = 42\nprint(x)"
    await tool.handler(
        {
            "experiment_id": running_experiment,
            "code": code,
            "description": "Store artifact test",
        }
    )

    # Check artifact was stored
    artifact_path = f"experiments/{running_experiment}/run_1.py"
    stored = await lab.artifact_store.load(artifact_path)
    assert stored is not None
    assert stored.decode() == code


async def test_run_experiment_code_tracks_code_run(lab, running_experiment):
    """run_experiment_code appends a CodeRun to experiment.result."""
    tools = {t.name: t for t in create_experiment_tools(lab)}
    tool = tools["run_experiment_code"]

    await tool.handler(
        {
            "experiment_id": running_experiment,
            "code": "print('test')",
            "description": "Track code run",
        }
    )

    exp = await lab.experiment_store.load(running_experiment)
    assert exp.result is not None
    assert len(exp.result.code_runs) == 1
    cr = exp.result.code_runs[0]
    assert cr.run_number == 1
    assert cr.description == "Track code run"
    assert cr.exit_code == 0


async def test_run_experiment_code_multiple_runs(lab, running_experiment):
    """Multiple run_experiment_code calls increment run_number."""
    tools = {t.name: t for t in create_experiment_tools(lab)}
    tool = tools["run_experiment_code"]

    await tool.handler({"experiment_id": running_experiment, "code": "print(1)"})
    result2 = await tool.handler({"experiment_id": running_experiment, "code": "print(2)"})

    assert result2.data["run_number"] == 2

    exp = await lab.experiment_store.load(running_experiment)
    assert len(exp.result.code_runs) == 2


async def test_run_experiment_code_not_running(lab):
    """run_experiment_code fails if experiment is not RUNNING."""
    service = ExperimentService(lab)
    exp = Experiment(
        domain_id="test-domain",
        hypothesis=Hypothesis(description="Pending test"),
    )
    exp_id = await service.create(exp)
    # Don't call service.run() — experiment stays PENDING

    tools = {t.name: t for t in create_experiment_tools(lab)}
    result = await tools["run_experiment_code"].handler(
        {
            "experiment_id": exp_id,
            "code": "print('should not run')",
        }
    )

    assert result.error is not None
    assert "not in RUNNING state" in result.error


async def test_run_experiment_code_not_found(lab):
    """run_experiment_code fails gracefully for unknown experiment."""
    tools = {t.name: t for t in create_experiment_tools(lab)}
    result = await tools["run_experiment_code"].handler(
        {
            "experiment_id": "nonexistent-id",
            "code": "print('x')",
        }
    )
    assert result.error is not None


async def test_run_experiment_code_stores_meta_artifact(lab, running_experiment):
    """run_experiment_code stores a _meta.json artifact alongside the code."""
    tools = {t.name: t for t in create_experiment_tools(lab)}
    tool = tools["run_experiment_code"]

    await tool.handler(
        {
            "experiment_id": running_experiment,
            "code": "print('meta test')",
            "description": "Meta artifact check",
        }
    )

    meta_path = f"experiments/{running_experiment}/run_1_meta.json"
    stored = await lab.artifact_store.load(meta_path)
    assert stored is not None

    import json

    meta = json.loads(stored.decode())
    assert meta["run_number"] == 1
    assert meta["exit_code"] == 0
    assert meta["description"] == "Meta artifact check"


async def test_run_experiment_code_returns_code_path(lab, running_experiment):
    """run_experiment_code result includes the artifact code_path."""
    tools = {t.name: t for t in create_experiment_tools(lab)}
    tool = tools["run_experiment_code"]

    result = await tool.handler(
        {
            "experiment_id": running_experiment,
            "code": "pass",
        }
    )

    assert result.error is None
    assert result.data["code_path"] == f"experiments/{running_experiment}/run_1.py"


async def test_run_experiment_code_code_run_path_matches_artifact(lab, running_experiment):
    """The code_path stored in CodeRun matches the artifact key."""
    tools = {t.name: t for t in create_experiment_tools(lab)}
    tool = tools["run_experiment_code"]

    await tool.handler(
        {
            "experiment_id": running_experiment,
            "code": "x = 1",
            "description": "path consistency",
        }
    )

    exp = await lab.experiment_store.load(running_experiment)
    cr = exp.result.code_runs[0]
    stored = await lab.artifact_store.load(cr.code_path)
    assert stored is not None
