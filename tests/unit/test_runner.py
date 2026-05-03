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
