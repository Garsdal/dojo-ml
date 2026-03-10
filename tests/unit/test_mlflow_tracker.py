"""Unit tests for MlflowTracker."""

import pytest

from agentml.tracking.mlflow_tracker import MlflowTracker


@pytest.fixture
def tracker(tmp_path):
    uri = f"file:{tmp_path / 'mlruns'}"
    return MlflowTracker(tracking_uri=uri, experiment_name="unit-test")


async def test_log_and_get_metrics(tracker: MlflowTracker) -> None:
    await tracker.log_metrics("exp-001", {"accuracy": 0.95, "f1": 0.93})
    metrics = await tracker.get_metrics("exp-001")
    assert metrics["accuracy"] == pytest.approx(0.95)
    assert metrics["f1"] == pytest.approx(0.93)


async def test_log_params(tracker: MlflowTracker) -> None:
    await tracker.log_params("exp-002", {"model": "xgboost", "lr": 0.01})
    run_id = tracker._get_or_create_run("exp-002")
    run = tracker._client.get_run(run_id)
    assert run.data.params["model"] == "xgboost"
    assert run.data.params["lr"] == "0.01"


async def test_nested_params_flattened(tracker: MlflowTracker) -> None:
    await tracker.log_params("exp-003", {"hp": {"lr": 0.01, "batch_size": 32}})
    run_id = tracker._get_or_create_run("exp-003")
    run = tracker._client.get_run(run_id)
    assert run.data.params["hp.lr"] == "0.01"
    assert run.data.params["hp.batch_size"] == "32"


async def test_run_reuse(tracker: MlflowTracker) -> None:
    """Same experiment_id should map to the same MLflow run."""
    await tracker.log_metrics("exp-reuse", {"m1": 1.0})
    run_id_1 = tracker._run_cache["exp-reuse"]
    await tracker.log_metrics("exp-reuse", {"m2": 2.0})
    run_id_2 = tracker._run_cache["exp-reuse"]
    assert run_id_1 == run_id_2

    metrics = await tracker.get_metrics("exp-reuse")
    assert metrics["m1"] == pytest.approx(1.0)
    assert metrics["m2"] == pytest.approx(2.0)


async def test_multiple_experiments_get_distinct_runs(tracker: MlflowTracker) -> None:
    """Different experiment_ids get different MLflow runs."""
    await tracker.log_metrics("exp-a", {"acc": 0.9})
    await tracker.log_metrics("exp-b", {"acc": 0.8})
    assert tracker._run_cache["exp-a"] != tracker._run_cache["exp-b"]


async def test_close_does_not_raise(tracker: MlflowTracker) -> None:
    await tracker.close()
