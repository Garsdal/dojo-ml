"""Unit tests for the framework-owned runner module."""

from __future__ import annotations

import json

from dojo.runtime.runner import (
    ERROR_MARKER,
    METRICS_MARKER,
    parse_runner_stdout,
    render_runner,
)


def test_render_runner_inserts_canonical_first_on_path():
    """Phase 4 contract: canonical wins over workspace for `evaluate` import."""
    code = render_runner(
        train_module="__dojo_train_1",
        canonical_dir="/canonical",
        workspace_dir="/workspace",
        callsite="metrics = evaluate(train())",
    )
    canonical_idx = code.index(repr("/canonical"))
    workspace_idx = code.index(repr("/workspace"))
    # render emits `sys.path.insert(0, workspace)` then `sys.path.insert(0, canonical)`
    # so the final ordering is [canonical, workspace, ...].
    assert workspace_idx < canonical_idx


def test_parse_runner_stdout_metrics():
    metrics = {"rmse": 1.0, "r2": 0.9, "mae": 0.5}
    stdout = f"some setup logs\n{METRICS_MARKER}{json.dumps(metrics)}\n"
    out = parse_runner_stdout(stdout)
    assert out.kind == "metrics"
    assert out.metrics == metrics


def test_parse_runner_stdout_error():
    err = {"type": "ValueError", "message": "boom", "traceback": "..."}
    stdout = f"{ERROR_MARKER}{json.dumps(err)}\n"
    out = parse_runner_stdout(stdout)
    assert out.kind == "error"
    assert out.error["message"] == "boom"


def test_parse_runner_stdout_no_marker():
    out = parse_runner_stdout("just some random output\n")
    assert out.kind == "no_marker"
    assert out.metrics == {}


def test_parse_runner_stdout_finds_marker_amid_noise():
    """train() may print debug; the parser scans in reverse for the marker."""
    metrics = {"rmse": 1.0, "r2": 0.9, "mae": 0.5}
    stdout = (
        "epoch 1 loss=0.5\n"
        "epoch 2 loss=0.3\n"
        f"{METRICS_MARKER}{json.dumps(metrics)}\n"
        "wrap-up text after\n"
    )
    out = parse_runner_stdout(stdout)
    assert out.kind == "metrics"
    assert out.metrics == metrics


def test_parse_runner_stdout_ignores_malformed_markers():
    """A marker line with broken JSON should not stop the scan from finding a
    later good marker (or falling through to no_marker)."""
    stdout = f"{METRICS_MARKER}not-json\n"
    out = parse_runner_stdout(stdout)
    assert out.kind == "no_marker"


def test_parse_runner_stdout_metrics_must_be_dict():
    stdout = f"{METRICS_MARKER}[1, 2, 3]\n"
    out = parse_runner_stdout(stdout)
    assert out.kind == "no_marker"


# ---------------------------------------------------------------------------
# Tests for callsite parameterisation (Task B2)
# ---------------------------------------------------------------------------


def test_render_runner_inlines_callsite_from_spec():
    from dojo.core.task import TASK_TYPE_REGISTRY, TaskType

    spec = TASK_TYPE_REGISTRY[TaskType.REGRESSION]
    code = render_runner(
        train_module="__dojo_train",
        canonical_dir="/canon",
        workspace_dir="/ws",
        callsite=spec.runner_callsite,
    )
    assert spec.runner_callsite in code
    assert "from __dojo_train import train" in code
    assert "from evaluate import evaluate" in code


def test_render_runner_uses_provided_callsite_literal():
    custom = "metrics = {'rmse': 0.0, 'r2': 0.0, 'mae': 0.0}"
    code = render_runner(
        train_module="__dojo_train",
        canonical_dir="/canon",
        workspace_dir="/ws",
        callsite=custom,
    )
    assert custom in code


def test_render_runner_inlines_prelude_before_callsite():
    code = render_runner(
        train_module="__dojo_train",
        canonical_dir="/canon",
        workspace_dir="/ws",
        prelude="from foo import bar\n    baz = bar()",
        callsite="metrics = baz()",
    )
    assert "from foo import bar" in code
    assert "baz = bar()" in code
    # Prelude must precede callsite
    assert code.index("baz = bar()") < code.index("metrics = baz()")


def test_render_runner_omits_load_data_when_no_prelude():
    """Default prelude is empty — runner does not assume load_data exists."""
    code = render_runner(
        train_module="__dojo_train",
        canonical_dir="/canon",
        workspace_dir="/ws",
        callsite="metrics = {'rmse': 0.0, 'r2': 0.0, 'mae': 0.0}",
    )
    assert "from load_data import load_data" not in code
    assert "X_train, X_test, y_train, y_test" not in code
