"""Framework-owned runner for the function-based train/evaluate contract.

Each ``run_experiment`` call writes the agent's training code as a Python
module, writes this runner stub alongside, then executes the runner. The
runner imports the agent's ``train()`` and the canonical ``evaluate()`` in the
same Python process — ``train()``'s output (e.g. a 4128-element y_pred for
California housing) never leaves memory.

The runner emits exactly one marker line on stdout —
``__DOJO_METRICS__:{...}`` on success or ``__DOJO_ERROR__:{...}`` on failure —
which the framework parses to record metrics on the experiment. This keeps
the IPC payload tiny (~100 bytes) and robust to any other prints ``train()``
might do.

This module is the single source of truth for "how an experiment is shaped".
Sandbox-agnostic: switching from ``LocalSandbox`` to a Docker or remote
sandbox later is a new ``Sandbox`` impl. The runner template is unchanged.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

METRICS_MARKER = "__DOJO_METRICS__:"
ERROR_MARKER = "__DOJO_ERROR__:"


def render_runner(
    *,
    train_module: str,
    canonical_dir: str,
    workspace_dir: str,
    train_dir: str | None = None,
) -> str:
    """Render the runner script as a module string.

    sys.path priority (last-inserted wins):
      1. ``train_dir`` — where the per-experiment ``__dojo_train.py`` lives
         (under .dojo/domains/{id}/runs/{eid}/), if provided.
      2. ``canonical_dir`` — frozen ``load_data`` / ``evaluate`` tools.
      3. ``workspace_dir`` — the user's repo, for their own imports.

    Canonical-before-workspace ensures the frozen tools resolve correctly even
    if the user's repo also has files named ``load_data.py`` / ``evaluate.py``.
    """
    extra_paths = ""
    if train_dir is not None:
        extra_paths = f"sys.path.insert(0, {train_dir!r})\n"
    return f"""\
import json, sys, traceback
sys.path.insert(0, {workspace_dir!r})
sys.path.insert(0, {canonical_dir!r})
{extra_paths}
try:
    from {train_module} import train
    from evaluate import evaluate
    metrics = evaluate(train())
    print({METRICS_MARKER!r} + json.dumps(metrics))
except Exception as e:
    print({ERROR_MARKER!r} + json.dumps({{
        "type": type(e).__name__,
        "message": str(e),
        "traceback": traceback.format_exc(),
    }}))
    sys.exit(1)
"""


@dataclass
class RunnerOutcome:
    """Typed result of parsing the runner's stdout.

    ``kind`` is one of:
      - ``"metrics"`` — train+evaluate succeeded; metrics dict is populated.
      - ``"error"``   — runner caught an exception; error dict is populated.
      - ``"no_marker"`` — no marker line on stdout; usually means the
        subprocess crashed before reaching the try/except (e.g. import error
        in the runner itself, segfault, OOM kill).
    """

    kind: str
    metrics: dict[str, Any] = field(default_factory=dict)
    error: dict[str, Any] = field(default_factory=dict)


def parse_runner_stdout(stdout: str) -> RunnerOutcome:
    """Find the last marker line on ``stdout`` and parse the JSON tail.

    Scans in reverse so noise from ``train()`` doesn't fool us. Falls through
    to ``no_marker`` if no parseable marker is found.
    """
    for raw in reversed(stdout.splitlines()):
        line = raw.rstrip()
        if line.startswith(METRICS_MARKER):
            try:
                metrics = json.loads(line[len(METRICS_MARKER) :])
            except json.JSONDecodeError:
                continue
            if not isinstance(metrics, dict):
                continue
            return RunnerOutcome(kind="metrics", metrics=metrics)
        if line.startswith(ERROR_MARKER):
            try:
                error = json.loads(line[len(ERROR_MARKER) :])
            except json.JSONDecodeError:
                continue
            if not isinstance(error, dict):
                continue
            return RunnerOutcome(kind="error", error=error)
    return RunnerOutcome(kind="no_marker")


def format_runner_error(stdout: str, stderr: str, exit_code: int) -> str:
    """Build a human-readable error message from a no-marker / failed runner.

    Used by ``run_experiment`` to populate ``experiment.result.error`` when
    the runner produced no usable marker. Truncates so a multi-MB stderr
    doesn't blow up the JSON store.
    """
    return (
        f"runner produced no metrics marker (exit={exit_code}). "
        f"stderr: {stderr.strip()[:500]}\nstdout tail: {stdout.strip()[-500:]}"
    )
