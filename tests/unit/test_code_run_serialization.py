"""CodeRun.artifact_paths round-trips through JSON serialization."""

import json
from datetime import UTC, datetime

import pytest

from dojo.core.experiment import CodeRun, Experiment, ExperimentResult
from dojo.storage.local.experiment import LocalExperimentStore
from dojo.utils.serialization import to_json


def test_code_run_default_artifact_paths_is_empty_list():
    run = CodeRun(run_number=1, code_path="x.py")
    assert run.artifact_paths == []


def test_code_run_artifact_paths_round_trip():
    run = CodeRun(
        run_number=1,
        code_path="x.py",
        description="hi",
        exit_code=0,
        duration_ms=12.5,
        timestamp=datetime(2026, 5, 4, tzinfo=UTC),
        artifact_paths=["experiments/abc/artifacts/plot.html"],
    )
    payload = json.loads(to_json(run))
    assert payload["artifact_paths"] == ["experiments/abc/artifacts/plot.html"]


@pytest.mark.asyncio
async def test_artifact_paths_round_trip_through_local_experiment_store(tmp_path):
    store = LocalExperimentStore(base_dir=tmp_path)
    experiment = Experiment(
        domain_id="d1",
        result=ExperimentResult(
            code_runs=[
                CodeRun(
                    run_number=1,
                    code_path="x.py",
                    artifact_paths=["experiments/abc/artifacts/plot.html"],
                )
            ]
        ),
    )
    await store.save(experiment)
    loaded = await store.load(experiment.id)
    assert loaded is not None
    assert loaded.result is not None
    assert len(loaded.result.code_runs) == 1
    assert loaded.result.code_runs[0].artifact_paths == [
        "experiments/abc/artifacts/plot.html"
    ]
