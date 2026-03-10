"""Unit tests for the FileTracker."""

import json
from pathlib import Path

import pytest

from agentml.tracking.file_tracker import FileTracker


@pytest.fixture
def tracker(tmp_path: Path) -> FileTracker:
    return FileTracker(base_dir=tmp_path / "tracking")


async def test_log_and_get_metrics(tracker: FileTracker) -> None:
    await tracker.log_metrics("exp-001", {"acc": 0.95})
    metrics = await tracker.get_metrics("exp-001")
    assert metrics["acc"] == 0.95


async def test_metrics_accumulate(tracker: FileTracker) -> None:
    await tracker.log_metrics("exp-001", {"acc": 0.95})
    await tracker.log_metrics("exp-001", {"f1": 0.93})
    metrics = await tracker.get_metrics("exp-001")
    assert metrics == {"acc": 0.95, "f1": 0.93}


async def test_log_params(tracker: FileTracker) -> None:
    await tracker.log_params("exp-001", {"model": "xgboost"})
    params_file = tracker._experiment_dir("exp-001") / "params.json"
    params = json.loads(params_file.read_text())
    assert params["model"] == "xgboost"


async def test_get_metrics_unknown_experiment(tracker: FileTracker) -> None:
    metrics = await tracker.get_metrics("does-not-exist")
    assert metrics == {}


async def test_close_is_noop(tracker: FileTracker) -> None:
    await tracker.close()  # Should not raise
