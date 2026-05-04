"""CodeRun.artifact_paths round-trips through JSON serialization."""

import json
from datetime import UTC, datetime

from dojo.core.experiment import CodeRun
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
