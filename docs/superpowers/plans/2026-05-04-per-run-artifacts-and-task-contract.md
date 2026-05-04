# Per-run Artifacts + Task Contract Decoupling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give every experiment its own artifacts directory (auto-ingested via `ArtifactStore` + tracking) and extend the regression `evaluate`/`train` contracts so agent code receives data splits as parameters instead of calling `load_data` internally. Move task-type-specific call patterns out of `runner.py` and `tool_verifier.py` into `TaskTypeSpec` so future task types are a registry-only addition.

**Architecture:**
- Group A wires per-run artifacts end-to-end (env var → ingestion → CodeRun field) — independent change, ships first.
- Group B refactors `render_runner` and `_build_fixtures` to consume new `TaskTypeSpec` fields (`runner_callsite`, `verifier_fixture_keys`) without behavior change.
- Group C uses those new fields to swap in the extended `train(X_train, y_train, X_test)` and `evaluate(y_pred, *, X_train, X_test, y_train, y_test)` contracts.
- Group D adds `contract_version` to `TaskTypeSpec` and `assert_ready` rejects tasks frozen against an older version, forcing a one-time re-verify.

**Tech Stack:** Python 3.13, pydantic, FastAPI, pytest (asyncio_mode=auto), structlog, Ruff. All tests run against real adapters in tmp dirs (no mocking) per [tests/conftest.py](tests/conftest.py).

**Spec:** [docs/superpowers/specs/2026-05-04-per-run-artifacts-and-task-contract-design.md](docs/superpowers/specs/2026-05-04-per-run-artifacts-and-task-contract-design.md)

**Pre-existing surface that the spec was wrong about (factor into plan):**
- `TrackingConnector.log_artifact` **already exists** on the interface and all three implementations ([interfaces/tracking.py:31](src/dojo/interfaces/tracking.py#L31), `mlflow_tracker.py:90`, `file_tracker.py:37`, `noop_tracker.py:17`). No interface change needed — just call it from the new ingestion code.
- The field on `TaskTypeSpec` is **`required_tools`**, not `tool_contracts` ([core/task.py:59](src/dojo/core/task.py#L59)).
- `train` is **not** in `required_tools` (it's submitted per-experiment, not generated). Its contract lives in the prompt + runner callsite, not in a `ToolContract`.

---

## File Structure

| File | Role |
|---|---|
| [src/dojo/core/experiment.py](src/dojo/core/experiment.py) | Add `CodeRun.artifact_paths` |
| [src/dojo/core/task.py](src/dojo/core/task.py) | Add `runner_callsite`, `verifier_fixture_keys`, `contract_version` to `TaskTypeSpec`; extend regression `evaluate` ToolContract; rewrite `_REGRESSION_PROMPT` |
| [src/dojo/runtime/runner.py](src/dojo/runtime/runner.py) | Refactor `render_runner` to consume `runner_callsite` |
| [src/dojo/runtime/tool_verifier.py](src/dojo/runtime/tool_verifier.py) | Refactor `_build_fixtures` to consume `verifier_fixture_keys`; remove hardcoded regression branch |
| [src/dojo/runtime/task_service.py](src/dojo/runtime/task_service.py) | Store `contract_version` on freeze; reject stale at `assert_ready` |
| [src/dojo/tools/experiments.py](src/dojo/tools/experiments.py) | Create per-run artifacts dir, set `DOJO_ARTIFACTS_DIR`, post-run ingest |
| `tests/unit/test_runner.py` (new) | Cover `render_runner` against new `runner_callsite` field |
| `tests/unit/test_tool_verifier_fixtures.py` (new) | Cover `_build_fixtures` against new `verifier_fixture_keys` |
| `tests/unit/test_code_run_serialization.py` (new) | Cover `CodeRun.artifact_paths` JSON round-trip |
| `tests/integration/test_run_experiment_artifacts.py` (new) | End-to-end: agent writes file in `DOJO_ARTIFACTS_DIR`, framework ingests + populates `code_runs[].artifact_paths` |
| `tests/integration/test_task_contract_version.py` (new) | Stale `contract_version` blocks `assert_ready` with clear error |

---

## Group A — Per-run artifacts (independent ship)

### Task A1: Add `artifact_paths` field to `CodeRun`

**Files:**
- Modify: [src/dojo/core/experiment.py](src/dojo/core/experiment.py) (the `CodeRun` dataclass at lines 19-28)
- Test: `tests/unit/test_code_run_serialization.py` (new)

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_code_run_serialization.py`:

```python
"""CodeRun.artifact_paths round-trips through JSON serialization."""

from datetime import UTC, datetime

from dojo.core.experiment import CodeRun
from dojo.utils.serialization import to_json
import json


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
```

- [ ] **Step 2: Run test to verify it fails**

```
uv run pytest tests/unit/test_code_run_serialization.py -v
```
Expected: FAIL — `artifact_paths` is not a field on `CodeRun`.

- [ ] **Step 3: Add the field**

In [src/dojo/core/experiment.py](src/dojo/core/experiment.py), update the `CodeRun` dataclass:

```python
@dataclass
class CodeRun:
    """Record of a single code execution within an experiment."""

    run_number: int = 0
    code_path: str = ""
    description: str = ""
    exit_code: int = 0
    duration_ms: float = 0.0
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    artifact_paths: list[str] = field(default_factory=list)
```

- [ ] **Step 4: Run test to verify it passes**

```
uv run pytest tests/unit/test_code_run_serialization.py -v
```
Expected: PASS.

- [ ] **Step 5: Commit**

```
git add src/dojo/core/experiment.py tests/unit/test_code_run_serialization.py
git commit -m "feat(experiment): add CodeRun.artifact_paths field"
```

---

### Task A2: Set `DOJO_ARTIFACTS_DIR` env var + create dir

**Files:**
- Modify: [src/dojo/tools/experiments.py:95-125](src/dojo/tools/experiments.py#L95-L125) (the `run_experiment` body, around the `runs_dir` block and `lab.sandbox.execute` call)
- Test: covered by Task A4's integration test (we test env-injection end-to-end there)

- [ ] **Step 1: Write the failing assertion (deferred)**

This task has no isolated unit test — the env var is consumed by user code in a subprocess, and the user-visible behavior is "files persist into the artifacts dir." That's covered by the integration test in Task A4. We still ship this task standalone so A4 has the foundation it needs.

- [ ] **Step 2: Modify `run_experiment` to create the dir + add the env var**

In [src/dojo/tools/experiments.py](src/dojo/tools/experiments.py), inside `run_experiment`, find the block:

```python
        runs_dir = task_service.runs_dir(domain_id, experiment_id)
        runs_dir.mkdir(parents=True, exist_ok=True)
```

(currently line 97-98). Add the artifacts dir below it:

```python
        runs_dir = task_service.runs_dir(domain_id, experiment_id)
        runs_dir.mkdir(parents=True, exist_ok=True)
        artifacts_dir = runs_dir / "artifacts"
        artifacts_dir.mkdir(parents=True, exist_ok=True)
```

Then find the `lab.sandbox.execute` call (currently lines 117-125):

```python
        ws = domain.workspace
        exec_result = await lab.sandbox.execute(
            runner_code,
            cwd=str(workspace_path),
            python_path=ws.python_path,
            env_vars=ws.env_vars or None,
            name="__dojo_runner",
            script_dir=str(runs_dir),
        )
```

Replace with:

```python
        ws = domain.workspace
        env_vars = dict(ws.env_vars or {})
        env_vars["DOJO_ARTIFACTS_DIR"] = str(artifacts_dir)
        exec_result = await lab.sandbox.execute(
            runner_code,
            cwd=str(workspace_path),
            python_path=ws.python_path,
            env_vars=env_vars,
            name="__dojo_runner",
            script_dir=str(runs_dir),
        )
```

- [ ] **Step 3: Run the existing experiment tests to confirm no regression**

```
uv run pytest tests/ -k experiment -v
```
Expected: PASS — the env var is additive, no existing test reads it.

- [ ] **Step 4: Commit**

```
git add src/dojo/tools/experiments.py
git commit -m "feat(experiments): create per-run artifacts dir and expose via DOJO_ARTIFACTS_DIR"
```

---

### Task A3: Post-run ingestion of artifacts dir

**Files:**
- Modify: [src/dojo/tools/experiments.py:127-148](src/dojo/tools/experiments.py#L127-L148) (the `CodeRun` append + outcome handling)
- Test: covered by Task A4's integration test

- [ ] **Step 1: Add a private async helper at module level**

In [src/dojo/tools/experiments.py](src/dojo/tools/experiments.py), add this helper *above* `_finalise_experiment` (near the bottom of the file):

```python
async def _ingest_artifacts(
    *,
    lab: LabEnvironment,
    experiment_id: str,
    artifacts_dir: Path,
) -> list[str]:
    """Walk the per-run artifacts dir, register each file with ArtifactStore,
    and forward to the tracking connector. Returns the list of stored
    artifact keys (suitable for CodeRun.artifact_paths). Failures are logged
    and swallowed so artifact-ingestion problems never fail the run.
    """
    paths: list[str] = []
    if not artifacts_dir.exists():
        return paths
    for file in sorted(artifacts_dir.rglob("*")):
        if not file.is_file():
            continue
        relative = file.relative_to(artifacts_dir).as_posix()
        key = f"experiments/{experiment_id}/artifacts/{relative}"
        try:
            await lab.artifact_store.save(key, file.read_bytes())
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "artifact_ingest_failed",
                experiment_id=experiment_id,
                file=str(file),
                error=str(exc),
            )
            continue
        paths.append(key)
        try:
            await lab.tracking.log_artifact(experiment_id, str(file))
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "artifact_track_failed",
                experiment_id=experiment_id,
                file=str(file),
                error=str(exc),
            )
    return paths
```

- [ ] **Step 2: Wire it into `run_experiment`**

Locate the `experiment.result.code_runs.append(...)` block (currently lines 129-138):

```python
        experiment.result.code_runs.append(
            CodeRun(
                run_number=run_number,
                code_path=artifact_path,
                description=hypothesis_text,
                exit_code=exec_result.exit_code,
                duration_ms=exec_result.duration_ms,
                timestamp=datetime.now(UTC),
            )
        )
```

Replace with:

```python
        ingested = await _ingest_artifacts(
            lab=lab,
            experiment_id=experiment_id,
            artifacts_dir=artifacts_dir,
        )
        experiment.result.code_runs.append(
            CodeRun(
                run_number=run_number,
                code_path=artifact_path,
                description=hypothesis_text,
                exit_code=exec_result.exit_code,
                duration_ms=exec_result.duration_ms,
                timestamp=datetime.now(UTC),
                artifact_paths=ingested,
            )
        )
```

- [ ] **Step 3: Run existing experiment tests to confirm nothing regresses**

```
uv run pytest tests/ -k experiment -v
```
Expected: PASS — empty artifacts dir produces empty list, append behavior unchanged.

- [ ] **Step 4: Commit**

```
git add src/dojo/tools/experiments.py
git commit -m "feat(experiments): ingest per-run artifacts into store + tracking"
```

---

### Task A4: Integration test — end-to-end artifacts ingestion

**Files:**
- Create: `tests/integration/test_run_experiment_artifacts.py`

- [ ] **Step 1: Write the integration test**

Create `tests/integration/test_run_experiment_artifacts.py`:

```python
"""End-to-end: agent's train code writes a file under DOJO_ARTIFACTS_DIR;
framework ingests it via ArtifactStore + tracking and records on CodeRun."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from dojo.core.domain import Domain, DomainTool, Workspace, WorkspaceSource
from dojo.core.task import TASK_TYPE_REGISTRY, TaskType
from dojo.core.task import ToolContract  # noqa: F401  re-export sanity
from dojo.runtime.task_service import TaskService
from dojo.tools.experiments import create_experiment_tools

# Minimal valid load_data + evaluate, plus a train script that writes a file
# into DOJO_ARTIFACTS_DIR — this is what the new prompt will instruct the
# agent to do.

_LOAD_DATA = textwrap.dedent(
    """
    def load_data():
        X_train = [[1.0], [2.0], [3.0]]
        X_test = [[4.0], [5.0]]
        y_train = [1.0, 2.0, 3.0]
        y_test = [4.0, 5.0]
        return X_train, X_test, y_train, y_test
    """
)

_EVALUATE = textwrap.dedent(
    """
    from load_data import load_data

    def evaluate(y_pred):
        _, _, _, y_test = load_data()
        diffs = [abs(a - b) for a, b in zip(y_test, y_pred)]
        mae = sum(diffs) / len(diffs)
        return {"rmse": mae, "r2": 0.0, "mae": mae}
    """
)

_TRAIN = textwrap.dedent(
    """
    import os
    from pathlib import Path

    def train():
        artifacts = Path(os.environ["DOJO_ARTIFACTS_DIR"])
        (artifacts / "evaluation_summary.html").write_text("<html>ok</html>")
        return [4.0, 5.0]
    """
)


@pytest.mark.asyncio
async def test_run_experiment_ingests_artifacts(lab, settings, tmp_path):
    workspace = Workspace(
        source=WorkspaceSource.LOCAL,
        path=str(tmp_path / "ws"),
        ready=True,
        python_path=None,
    )
    Path(workspace.path).mkdir(parents=True, exist_ok=True)
    domain = Domain(
        name="t",
        prompt="t",
        workspace=workspace,
    )
    await lab.domain_store.save(domain)

    task_service = TaskService(lab)
    await task_service.create(domain.id, task_type=TaskType.REGRESSION)

    spec = TASK_TYPE_REGISTRY[TaskType.REGRESSION]
    domain = await lab.domain_store.load(domain.id)
    domain.task.tools = [
        DomainTool(
            name="load_data",
            module_filename="load_data.py",
            entrypoint="load_data",
            code=_LOAD_DATA,
        ),
        DomainTool(
            name="evaluate",
            module_filename="evaluate.py",
            entrypoint="evaluate",
            code=_EVALUATE,
        ),
    ]
    await lab.domain_store.save(domain)
    await task_service.freeze(domain.id, skip_verification=True)

    tools = {t.name: t for t in create_experiment_tools(lab)}
    result = await tools["run_experiment"].handler(
        {
            "domain_id": domain.id,
            "hypothesis": "writes an artifact",
            "train_code": _TRAIN,
        }
    )

    assert result.error is None, result.error
    assert result.data["status"] == "completed"

    experiment_id = result.data["experiment_id"]
    artifacts_dir = (
        Path(settings.storage.base_dir)
        / "domains" / domain.id / "runs" / experiment_id / "artifacts"
    )
    assert (artifacts_dir / "evaluation_summary.html").read_text() == "<html>ok</html>"

    saved = await lab.artifact_store.list(prefix=f"experiments/{experiment_id}/artifacts/")
    assert any(p.endswith("evaluation_summary.html") for p in saved)

    exp = await lab.experiment_store.get(experiment_id)
    assert exp is not None
    assert len(exp.result.code_runs) == 1
    assert any(
        p.endswith("evaluation_summary.html") for p in exp.result.code_runs[0].artifact_paths
    )
```

- [ ] **Step 2: Run the test**

```
uv run pytest tests/integration/test_run_experiment_artifacts.py -v
```
Expected: PASS — Tasks A1–A3 already shipped the behavior.

If FAIL with "no module" / fixture errors: check that `lab` and `settings` fixtures in `tests/conftest.py` are unchanged from current main; the test mirrors existing integration tests' shape.

- [ ] **Step 3: Run lint + format**

```
just lint
```
Fix any issues (`just format` to auto-fix).

- [ ] **Step 4: Commit**

```
git add tests/integration/test_run_experiment_artifacts.py
git commit -m "test: e2e coverage for per-run artifact ingestion"
```

---

### Task A5: Update `_REGRESSION_PROMPT` for `DOJO_ARTIFACTS_DIR`

**Files:**
- Modify: [src/dojo/core/task.py](src/dojo/core/task.py) — the `_REGRESSION_PROMPT` template (lines 90-173)

(Note: this task only adds an artifacts paragraph to the prompt. The signature changes are part of Group C — keep this edit additive.)

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_code_run_serialization.py` (or create `tests/unit/test_regression_prompt.py` if you prefer split tests):

```python
from dojo.core.task import TASK_TYPE_REGISTRY, TaskType


def test_regression_prompt_mentions_artifacts_env_var():
    spec = TASK_TYPE_REGISTRY[TaskType.REGRESSION]
    assert "DOJO_ARTIFACTS_DIR" in spec.generation_prompt_template
```

- [ ] **Step 2: Run test to verify it fails**

```
uv run pytest tests/unit/test_code_run_serialization.py::test_regression_prompt_mentions_artifacts_env_var -v
```
Expected: FAIL — current prompt doesn't mention the env var.

- [ ] **Step 3: Add an `Artifacts` paragraph to the prompt**

In [src/dojo/core/task.py](src/dojo/core/task.py), find the line:

```
- For URLs, download via pandas/requests (the workspace has internet).
```

Below the closing of the `## How to read this` block (just before `## Output: exactly two Python modules`), insert:

```
## Artifacts
- The framework provides a per-run directory via the env var
  ``DOJO_ARTIFACTS_DIR``. Use it for any files you produce — plots, model
  checkpoints, intermediate CSVs.
- Read it as ``Path(os.environ["DOJO_ARTIFACTS_DIR"])``.
- Do **not** write to a relative ``artifacts/`` directory or anywhere else
  in the workspace — those paths are shared across experiments and the
  framework will not capture them. Files written under
  ``DOJO_ARTIFACTS_DIR`` are auto-registered into the artifact store and
  forwarded to the tracking backend.
```

- [ ] **Step 4: Run test to verify it passes**

```
uv run pytest tests/unit/test_code_run_serialization.py::test_regression_prompt_mentions_artifacts_env_var -v
```
Expected: PASS.

- [ ] **Step 5: Commit**

```
git add src/dojo/core/task.py tests/unit/test_code_run_serialization.py
git commit -m "feat(prompt): tell the agent to write artifacts to DOJO_ARTIFACTS_DIR"
```

---

## Group B — Polymorphic runner + verifier (no behavior change)

### Task B1: Add `runner_callsite`, `verifier_fixture_keys`, `contract_version` to `TaskTypeSpec`

**Files:**
- Modify: [src/dojo/core/task.py](src/dojo/core/task.py) (the `TaskTypeSpec` dataclass at lines 53-63 and the `TASK_TYPE_REGISTRY` regression entry at lines 175-219)
- Test: `tests/unit/test_task_type_spec_fields.py` (new)

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_task_type_spec_fields.py`:

```python
"""TaskTypeSpec exposes runner_callsite, verifier_fixture_keys, contract_version."""

from dojo.core.task import TASK_TYPE_REGISTRY, TaskType


def test_regression_spec_has_runner_callsite_using_evaluate_train():
    spec = TASK_TYPE_REGISTRY[TaskType.REGRESSION]
    assert "evaluate(" in spec.runner_callsite
    assert "train(" in spec.runner_callsite


def test_regression_spec_has_verifier_fixture_keys_for_evaluate():
    spec = TASK_TYPE_REGISTRY[TaskType.REGRESSION]
    assert "evaluate" in spec.verifier_fixture_keys
    assert "y_pred" in spec.verifier_fixture_keys["evaluate"]


def test_regression_spec_has_contract_version():
    spec = TASK_TYPE_REGISTRY[TaskType.REGRESSION]
    assert isinstance(spec.contract_version, int)
    assert spec.contract_version >= 1
```

- [ ] **Step 2: Run test to verify it fails**

```
uv run pytest tests/unit/test_task_type_spec_fields.py -v
```
Expected: FAIL — the fields don't exist.

- [ ] **Step 3: Add the fields**

In [src/dojo/core/task.py](src/dojo/core/task.py), update `TaskTypeSpec` (currently lines 53-63):

```python
@dataclass
class TaskTypeSpec:
    """Registry entry for a task type — shared across all domains of that type."""

    default_metric: str
    default_direction: Direction
    required_tools: list[ToolContract]
    generation_prompt_template: str
    config_schema: dict[str, Any]
    runner_callsite: str
    verifier_fixture_keys: dict[str, dict[str, str]]
    contract_version: int
    train_output_description: str = ""
```

Then update the regression entry in `TASK_TYPE_REGISTRY` to populate the new fields with the **current** call shape (no behavior change yet):

```python
TASK_TYPE_REGISTRY: ClassVar[dict[TaskType, TaskTypeSpec]] = {
    TaskType.REGRESSION: TaskTypeSpec(
        default_metric="rmse",
        default_direction=Direction.MINIMIZE,
        required_tools=[
            # ... existing load_data + evaluate contracts unchanged ...
        ],
        generation_prompt_template=_REGRESSION_PROMPT,
        config_schema={
            "required": ["data_path", "target_column"],
            "optional": {
                "test_split_ratio": 0.2,
                "feature_columns": [],
                "random_state": 42,
            },
        },
        runner_callsite="metrics = evaluate(train())",
        verifier_fixture_keys={
            "evaluate": {"y_pred": "y_test"},
        },
        contract_version=1,
        train_output_description=(
            "a flat list of float predictions for the test set, "
            "in the same order as X_test from load_data()"
        ),
    ),
}
```

(Keep the existing `required_tools` list as-is — Group C will edit them.)

- [ ] **Step 4: Run test to verify it passes**

```
uv run pytest tests/unit/test_task_type_spec_fields.py -v
```
Expected: PASS.

- [ ] **Step 5: Run the full test suite to confirm no regression**

```
just test
```
Expected: PASS for all existing tests.

- [ ] **Step 6: Commit**

```
git add src/dojo/core/task.py tests/unit/test_task_type_spec_fields.py
git commit -m "feat(task): add runner_callsite, verifier_fixture_keys, contract_version to TaskTypeSpec"
```

---

### Task B2: Refactor `render_runner` to consume `runner_callsite`

**Files:**
- Modify: [src/dojo/runtime/runner.py:30-68](src/dojo/runtime/runner.py#L30-L68) (the `render_runner` function)
- Modify: [src/dojo/tools/experiments.py:106-111](src/dojo/tools/experiments.py#L106-L111) (the call site that invokes `render_runner`)
- Test: `tests/unit/test_runner.py` (new)

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_runner.py`:

```python
"""render_runner consumes runner_callsite from TaskTypeSpec."""

from dojo.core.task import TASK_TYPE_REGISTRY, TaskType
from dojo.runtime.runner import render_runner


def test_render_runner_inlines_callsite_from_spec():
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


def test_render_runner_does_not_hardcode_train_evaluate_call():
    """The evaluate(train()) literal must come from the spec's callsite,
    not a hardcoded literal in render_runner itself."""
    custom = "metrics = {'rmse': 0.0, 'r2': 0.0, 'mae': 0.0}; train; evaluate"
    code = render_runner(
        train_module="__dojo_train",
        canonical_dir="/canon",
        workspace_dir="/ws",
        callsite=custom,
    )
    assert custom in code
    # Ensure the old hardcoded line is gone
    assert "metrics = evaluate(train())" not in code or custom == "metrics = evaluate(train())"
```

- [ ] **Step 2: Run test to verify it fails**

```
uv run pytest tests/unit/test_runner.py -v
```
Expected: FAIL — `render_runner` does not accept `callsite`.

- [ ] **Step 3: Refactor `render_runner`**

In [src/dojo/runtime/runner.py](src/dojo/runtime/runner.py), update the `render_runner` function:

```python
def render_runner(
    *,
    train_module: str,
    canonical_dir: str,
    workspace_dir: str,
    callsite: str,
    train_dir: str | None = None,
) -> str:
    """Render the runner script as a module string.

    The ``callsite`` is the task-type-specific Python expression(s) that wire
    train() and evaluate() together — it comes from
    ``TaskTypeSpec.runner_callsite`` so future task types are a registry-only
    addition (no edits to this file).

    sys.path priority (last-inserted wins):
      1. ``train_dir`` — where the per-experiment ``__dojo_train.py`` lives.
      2. ``canonical_dir`` — frozen ``load_data`` / ``evaluate`` tools.
      3. ``workspace_dir`` — the user's repo, for their own imports.
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
    from load_data import load_data
    from evaluate import evaluate
    X_train, X_test, y_train, y_test = load_data()
    {callsite}
    print({METRICS_MARKER!r} + json.dumps(metrics))
except Exception as e:
    print({ERROR_MARKER!r} + json.dumps({{
        "type": type(e).__name__,
        "message": str(e),
        "traceback": traceback.format_exc(),
    }}))
    sys.exit(1)
"""
```

Note: the runner now imports `load_data` and unpacks it before the callsite. This is a stable framework convention (regression's load_data returns 4-tuple). Future task types whose `load_data` returns something else will need the runner to be parameterised on the unpacking too — defer until that need exists.

- [ ] **Step 4: Update the call site in `experiments.py`**

In [src/dojo/tools/experiments.py](src/dojo/tools/experiments.py), find the `render_runner` invocation (currently around line 106-111):

```python
        runner_code = render_runner(
            train_module=train_module,
            canonical_dir=str(canonical_dir),
            workspace_dir=str(workspace_path),
            train_dir=str(runs_dir),
        )
```

Replace with:

```python
        from dojo.core.task import TASK_TYPE_REGISTRY  # local import to avoid cycle

        spec = TASK_TYPE_REGISTRY[domain.task.type]
        runner_code = render_runner(
            train_module=train_module,
            canonical_dir=str(canonical_dir),
            workspace_dir=str(workspace_path),
            train_dir=str(runs_dir),
            callsite=spec.runner_callsite,
        )
```

(If a top-level import of `TASK_TYPE_REGISTRY` is fine in `experiments.py`, hoist it. Check by running tests — if no cycle, prefer top-level.)

- [ ] **Step 5: Run runner test**

```
uv run pytest tests/unit/test_runner.py -v
```
Expected: PASS.

- [ ] **Step 6: Run full suite to confirm no behavior change**

```
just test
```
Expected: PASS — `runner_callsite="metrics = evaluate(train())"` from B1 keeps the runner behavior identical.

- [ ] **Step 7: Commit**

```
git add src/dojo/runtime/runner.py src/dojo/tools/experiments.py tests/unit/test_runner.py
git commit -m "refactor(runner): parameterise call shape via TaskTypeSpec.runner_callsite"
```

---

### Task B3: Refactor `_build_fixtures` and `_upstream_dep` to consume `verifier_fixture_keys`

**Files:**
- Modify: [src/dojo/runtime/tool_verifier.py:341-364](src/dojo/runtime/tool_verifier.py#L341-L364) (`_upstream_dep` and `_build_fixtures`)
- Modify: [src/dojo/runtime/tool_verifier.py:289-339](src/dojo/runtime/tool_verifier.py#L289-L339) (`_verify_in_dir` — the only caller)
- Test: `tests/unit/test_tool_verifier_fixtures.py` (new)

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_tool_verifier_fixtures.py`:

```python
"""_build_fixtures consumes verifier_fixture_keys from TaskTypeSpec."""

from dojo.core.task import TASK_TYPE_REGISTRY, TaskType
from dojo.runtime.tool_verifier import _build_fixtures


def test_build_fixtures_uses_spec_mapping_for_evaluate():
    spec = TASK_TYPE_REGISTRY[TaskType.REGRESSION]
    raw_outputs = {
        "load_data": {
            "X_train": [[1.0]],
            "X_test": [[2.0]],
            "y_train": [1.0],
            "y_test": [2.0],
        }
    }
    fixtures = _build_fixtures(spec, "evaluate", raw_outputs)
    assert fixtures is not None
    assert fixtures["y_pred"] == [2.0]


def test_build_fixtures_returns_none_for_unknown_tool():
    spec = TASK_TYPE_REGISTRY[TaskType.REGRESSION]
    fixtures = _build_fixtures(spec, "nonexistent_tool", {})
    assert fixtures is None


def test_build_fixtures_returns_none_when_upstream_missing():
    spec = TASK_TYPE_REGISTRY[TaskType.REGRESSION]
    fixtures = _build_fixtures(spec, "evaluate", {})  # no load_data outputs
    assert fixtures is None
```

- [ ] **Step 2: Run test to verify it fails**

```
uv run pytest tests/unit/test_tool_verifier_fixtures.py -v
```
Expected: FAIL — `_build_fixtures` currently takes `(task_type, tool_name, raw_outputs)`.

- [ ] **Step 3: Refactor `_build_fixtures`, `_upstream_dep`, and the `_verify_in_dir` callers**

In [src/dojo/runtime/tool_verifier.py](src/dojo/runtime/tool_verifier.py), replace the existing `_upstream_dep` (lines 341-345) and `_build_fixtures` (lines 348-364) with:

```python
def _upstream_dep(spec: Any, tool_name: str) -> str | None:
    """Return the upstream tool whose output `tool_name` depends on, if any.

    A tool depends on its upstream when ``verifier_fixture_keys[tool_name]``
    is non-empty — every fixture key is sourced from a previously-verified
    tool's output. Today every spec has a single upstream (``load_data``);
    if that ever changes, return the first upstream encountered (callers
    only care whether *some* upstream failed).
    """
    keys = spec.verifier_fixture_keys.get(tool_name) or {}
    if not keys:
        return None
    return "load_data"


def _build_fixtures(
    spec: Any,
    tool_name: str,
    raw_outputs: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    """Map an upstream tool's outputs into fixtures for the current tool.

    The mapping comes from ``TaskTypeSpec.verifier_fixture_keys[tool_name]``:
    a dict of ``{contract_param: load_data_output_key}``. For regression's
    ``evaluate``, ``y_pred`` is sourced from ``y_test`` (perfect-prediction
    fixture).
    """
    mapping = spec.verifier_fixture_keys.get(tool_name)
    if not mapping:
        return None
    upstream = raw_outputs.get("load_data")
    if upstream is None:
        return None
    fixtures: dict[str, Any] = {}
    for param, source_key in mapping.items():
        if source_key not in upstream:
            return None
        fixtures[param] = upstream[source_key]
    return fixtures
```

Then update the two call sites in `_verify_in_dir` (lines 312 and 324):

```python
        upstream = _upstream_dep(spec, contract.name)
```

```python
        fixtures = _build_fixtures(spec, contract.name, raw_outputs)
```

(The `task` parameter on `_verify_in_dir` was used to derive `task.type`; the new signature passes `spec` directly so we can drop the type lookup. Verify by running tests.)

- [ ] **Step 4: Run unit tests**

```
uv run pytest tests/unit/test_tool_verifier_fixtures.py -v
```
Expected: PASS.

- [ ] **Step 5: Run full suite to confirm verification still works end-to-end**

```
just test
```
Expected: PASS — `verifier_fixture_keys={"evaluate": {"y_pred": "y_test"}}` from B1 produces the same fixtures the old hardcoded branch did.

- [ ] **Step 6: Commit**

```
git add src/dojo/runtime/tool_verifier.py tests/unit/test_tool_verifier_fixtures.py
git commit -m "refactor(verifier): drive fixtures from TaskTypeSpec.verifier_fixture_keys"
```

---

## Group C — Extended `evaluate` and `train` contracts

### Task C1: Extend regression `evaluate` ToolContract params_schema

**Files:**
- Modify: [src/dojo/core/task.py](src/dojo/core/task.py) — the `evaluate` `ToolContract` inside `TASK_TYPE_REGISTRY` (currently lines 194-206)
- Test: `tests/unit/test_task_type_spec_fields.py` (extend existing)

- [ ] **Step 1: Add a test for the new params_schema**

Append to `tests/unit/test_task_type_spec_fields.py`:

```python
def test_regression_evaluate_contract_includes_train_test_splits():
    spec = TASK_TYPE_REGISTRY[TaskType.REGRESSION]
    evaluate = next(c for c in spec.required_tools if c.name == "evaluate")
    for key in ["y_pred", "X_train", "X_test", "y_train", "y_test"]:
        assert key in evaluate.params_schema, (
            f"evaluate.params_schema missing {key!r}: {evaluate.params_schema}"
        )
```

- [ ] **Step 2: Run test to verify it fails**

```
uv run pytest tests/unit/test_task_type_spec_fields.py::test_regression_evaluate_contract_includes_train_test_splits -v
```
Expected: FAIL.

- [ ] **Step 3: Update the `evaluate` ToolContract**

In [src/dojo/core/task.py](src/dojo/core/task.py), replace the existing `evaluate` entry inside `required_tools`:

```python
            ToolContract(
                name="evaluate",
                description=(
                    "Evaluate model predictions; receives y_pred plus the "
                    "train/test splits so the agent code does not need to "
                    "call load_data internally."
                ),
                entrypoint="evaluate",
                module_filename="evaluate.py",
                params_schema={
                    "y_pred": "list of float",
                    "X_train": "list of lists (float)",
                    "X_test": "list of lists (float)",
                    "y_train": "list of float",
                    "y_test": "list of float",
                },
                returns_schema={
                    "rmse": "float",
                    "r2": "float",
                    "mae": "float",
                },
                return_kind="dict",
            ),
```

- [ ] **Step 4: Run test to verify it passes**

```
uv run pytest tests/unit/test_task_type_spec_fields.py::test_regression_evaluate_contract_includes_train_test_splits -v
```
Expected: PASS.

- [ ] **Step 5: Commit**

```
git add src/dojo/core/task.py tests/unit/test_task_type_spec_fields.py
git commit -m "feat(task): extend regression evaluate contract to receive train/test splits"
```

---

### Task C2: Update regression `runner_callsite` and `verifier_fixture_keys`

**Files:**
- Modify: [src/dojo/core/task.py](src/dojo/core/task.py) — the `TASK_TYPE_REGISTRY` regression entry's `runner_callsite` and `verifier_fixture_keys`

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_task_type_spec_fields.py`:

```python
def test_regression_runner_callsite_passes_data_to_train_and_evaluate():
    spec = TASK_TYPE_REGISTRY[TaskType.REGRESSION]
    callsite = spec.runner_callsite
    assert "train(X_train, y_train, X_test)" in callsite
    assert "X_train=X_train" in callsite
    assert "y_test=y_test" in callsite


def test_regression_verifier_fixture_keys_cover_extended_evaluate_params():
    spec = TASK_TYPE_REGISTRY[TaskType.REGRESSION]
    keys = spec.verifier_fixture_keys["evaluate"]
    for param in ["y_pred", "X_train", "X_test", "y_train", "y_test"]:
        assert param in keys
    assert keys["y_pred"] == "y_test"
    assert keys["X_train"] == "X_train"
```

- [ ] **Step 2: Run tests to verify they fail**

```
uv run pytest tests/unit/test_task_type_spec_fields.py -v
```
Expected: 2 FAILs.

- [ ] **Step 3: Update the regression spec**

In [src/dojo/core/task.py](src/dojo/core/task.py), update the regression entry's `runner_callsite` and `verifier_fixture_keys`:

```python
        runner_callsite=(
            "y_pred = train(X_train, y_train, X_test)\n"
            "    metrics = evaluate("
            "y_pred, "
            "X_train=X_train, "
            "X_test=X_test, "
            "y_train=y_train, "
            "y_test=y_test)"
        ),
        verifier_fixture_keys={
            "evaluate": {
                "y_pred": "y_test",
                "X_train": "X_train",
                "X_test": "X_test",
                "y_train": "y_train",
                "y_test": "y_test",
            },
        },
```

(The leading `    ` on the `metrics = evaluate(...)` line aligns with the runner template's `try:` block indentation. The runner template renders `{callsite}` at 4-space indent — verify by inspecting the rendered output in the next step.)

- [ ] **Step 4: Run tests to verify they pass**

```
uv run pytest tests/unit/test_task_type_spec_fields.py -v
```
Expected: PASS.

- [ ] **Step 5: Sanity-check the rendered runner**

```
uv run python -c "
from dojo.core.task import TASK_TYPE_REGISTRY, TaskType
from dojo.runtime.runner import render_runner
spec = TASK_TYPE_REGISTRY[TaskType.REGRESSION]
print(render_runner(
    train_module='__dojo_train',
    canonical_dir='/canon',
    workspace_dir='/ws',
    callsite=spec.runner_callsite,
))
"
```
Expected: clean Python with `y_pred = train(X_train, y_train, X_test)` and `metrics = evaluate(...)` correctly indented under `try:`. If indentation is off, adjust the leading whitespace inside `runner_callsite`.

- [ ] **Step 6: Commit**

```
git add src/dojo/core/task.py tests/unit/test_task_type_spec_fields.py
git commit -m "feat(task): runner+verifier wiring for extended train/evaluate signatures"
```

---

### Task C3: Rewrite the regression prompt for new signatures

**Files:**
- Modify: [src/dojo/core/task.py](src/dojo/core/task.py) — `_REGRESSION_PROMPT` template

- [ ] **Step 1: Write failing tests for the new prompt content**

Append to `tests/unit/test_task_type_spec_fields.py`:

```python
def test_regression_prompt_specifies_new_evaluate_signature():
    spec = TASK_TYPE_REGISTRY[TaskType.REGRESSION]
    prompt = spec.generation_prompt_template
    # New signature must appear; old single-param signature must not.
    assert "def evaluate(y_pred, *, X_train, X_test, y_train, y_test)" in prompt
    assert "def evaluate(y_pred):" not in prompt


def test_regression_prompt_forbids_load_data_inside_evaluate():
    spec = TASK_TYPE_REGISTRY[TaskType.REGRESSION]
    prompt = spec.generation_prompt_template
    # The agent must not be told to call load_data() inside evaluate.
    assert "from load_data import load_data" not in prompt or (
        "must not call" in prompt.lower() or "do not call" in prompt.lower()
    )


def test_regression_prompt_describes_train_signature():
    spec = TASK_TYPE_REGISTRY[TaskType.REGRESSION]
    prompt = spec.generation_prompt_template
    assert "train(X_train, y_train, X_test)" in prompt
```

- [ ] **Step 2: Run tests to verify they fail**

```
uv run pytest tests/unit/test_task_type_spec_fields.py -v
```
Expected: 3 FAILs.

- [ ] **Step 3: Rewrite Module 2 + Train sections of the prompt**

In [src/dojo/core/task.py](src/dojo/core/task.py), find this block in `_REGRESSION_PROMPT` (currently lines 144-152):

```
Module 2 — evaluate.py
- Defines a top-level function: `def evaluate(y_pred):`
  where `y_pred` is {train_output_description}.
- May import from load_data: `from load_data import load_data`.
- Reproduces the same split as load_data (call `load_data()` and unpack the
  4-tuple) to get y_test.
- Computes: rmse (float), r2 (float), mae (float).
- Returns a dict with exactly those three keys: {{"rmse": ..., "r2": ..., "mae": ...}}.
- Must NOT print to stdout — return only.
```

Replace with:

```
Module 2 — evaluate.py
- Defines a top-level function:
  `def evaluate(y_pred, *, X_train, X_test, y_train, y_test) -> dict`.
- Receives all data as parameters — do **not** call ``load_data`` inside
  ``evaluate``. The framework loads data once and passes the splits in.
- Computes: rmse (float), r2 (float), mae (float) against ``y_test``.
- Returns a dict with exactly those three keys: {{"rmse": ..., "r2": ..., "mae": ...}}.
- Must NOT print to stdout — return only.
- May write debugging / summary files into ``DOJO_ARTIFACTS_DIR`` (see
  the Artifacts section above).

## Train (agent's per-experiment code, written separately)
The framework expects the agent's training code to define:
  ``def train(X_train, y_train, X_test) -> y_pred``
where ``y_pred`` is {train_output_description}. The framework calls
``train`` with the splits from ``load_data()`` — do not call
``load_data`` from inside ``train`` either.
```

(The `{train_output_description}` placeholder remains in `TaskTypeSpec.train_output_description` and is filled at template-format time.)

- [ ] **Step 4: Run tests to verify they pass**

```
uv run pytest tests/unit/test_task_type_spec_fields.py -v
```
Expected: PASS.

- [ ] **Step 5: Commit**

```
git add src/dojo/core/task.py tests/unit/test_task_type_spec_fields.py
git commit -m "feat(prompt): teach the agent the new train/evaluate signatures"
```

---

### Task C4: Update integration test for new contracts

**Files:**
- Modify: `tests/integration/test_run_experiment_artifacts.py` (created in A4)

- [ ] **Step 1: Update the test fixtures to use new signatures**

Replace the `_EVALUATE` and `_TRAIN` constants in `tests/integration/test_run_experiment_artifacts.py`:

```python
_EVALUATE = textwrap.dedent(
    """
    def evaluate(y_pred, *, X_train, X_test, y_train, y_test):
        diffs = [abs(a - b) for a, b in zip(y_test, y_pred)]
        mae = sum(diffs) / len(diffs)
        return {"rmse": mae, "r2": 0.0, "mae": mae}
    """
)

_TRAIN = textwrap.dedent(
    """
    import os
    from pathlib import Path

    def train(X_train, y_train, X_test):
        artifacts = Path(os.environ["DOJO_ARTIFACTS_DIR"])
        (artifacts / "evaluation_summary.html").write_text("<html>ok</html>")
        return [4.0, 5.0]
    """
)
```

- [ ] **Step 2: Run the integration test**

```
uv run pytest tests/integration/test_run_experiment_artifacts.py -v
```
Expected: PASS — runner now calls `train(X_train, y_train, X_test)` and `evaluate(y_pred, X_train=..., ...)` matching the new spec callsite.

- [ ] **Step 3: Run the full test suite**

```
just test
```
Expected: PASS, **except** any pre-existing tests that pin the old single-param `evaluate(y_pred)` shape. Find them with:

```
git grep -n "def evaluate(y_pred):" tests/
```

For each match, update the test fixture's `evaluate` signature to the new keyword-only form (mirroring `_EVALUATE` above). Commit those updates as part of this task.

- [ ] **Step 4: Commit**

```
git add tests/
git commit -m "test: update fixtures for extended evaluate/train signatures"
```

---

## Group D — `contract_version` migration gate

### Task D1: Store `contract_version` on freeze; reject stale at `assert_ready`

**Files:**
- Modify: [src/dojo/runtime/task_service.py:107-149](src/dojo/runtime/task_service.py#L107-L149) (the `freeze` method) and [src/dojo/runtime/task_service.py:183-209](src/dojo/runtime/task_service.py#L183-L209) (`assert_ready`)
- Modify: [src/dojo/core/task.py](src/dojo/core/task.py) — bump regression's `contract_version` to 2
- Test: `tests/integration/test_task_contract_version.py` (new)

- [ ] **Step 1: Write the failing test**

Create `tests/integration/test_task_contract_version.py`:

```python
"""contract_version: stale frozen tasks must re-verify before agent runs."""

from __future__ import annotations

import pytest

from dojo.core.domain import Domain, DomainTool, Workspace, WorkspaceSource
from dojo.core.task import TASK_TYPE_REGISTRY, TaskType
from dojo.runtime.task_service import TaskNotReadyError, TaskService
from pathlib import Path


def _domain(tmp_path: Path, name: str = "t") -> Domain:
    return Domain(
        name=name,
        prompt="t",
        workspace=Workspace(
            source=WorkspaceSource.LOCAL,
            path=str(tmp_path / "ws"),
            ready=True,
        ),
    )


@pytest.mark.asyncio
async def test_freeze_stamps_contract_version_on_task(lab, tmp_path):
    domain = _domain(tmp_path)
    Path(domain.workspace.path).mkdir(parents=True, exist_ok=True)
    await lab.domain_store.save(domain)

    service = TaskService(lab)
    await service.create(domain.id, task_type=TaskType.REGRESSION)
    domain = await lab.domain_store.load(domain.id)
    domain.task.tools = [
        DomainTool(name="load_data", module_filename="load_data.py", code="x"),
        DomainTool(name="evaluate", module_filename="evaluate.py", code="x"),
    ]
    await lab.domain_store.save(domain)
    await service.freeze(domain.id, skip_verification=True)

    domain = await lab.domain_store.load(domain.id)
    spec = TASK_TYPE_REGISTRY[TaskType.REGRESSION]
    assert domain.task.config.get("contract_version") == spec.contract_version


@pytest.mark.asyncio
async def test_assert_ready_rejects_stale_contract_version(lab, tmp_path):
    domain = _domain(tmp_path)
    Path(domain.workspace.path).mkdir(parents=True, exist_ok=True)
    await lab.domain_store.save(domain)

    service = TaskService(lab)
    await service.create(domain.id, task_type=TaskType.REGRESSION)
    domain = await lab.domain_store.load(domain.id)
    domain.task.tools = [
        DomainTool(name="load_data", module_filename="load_data.py", code="x"),
        DomainTool(name="evaluate", module_filename="evaluate.py", code="x"),
    ]
    await lab.domain_store.save(domain)
    await service.freeze(domain.id, skip_verification=True)

    # Pretend the task was frozen against an older contract version.
    domain = await lab.domain_store.load(domain.id)
    domain.task.config["contract_version"] = 0
    await lab.domain_store.save(domain)

    with pytest.raises(TaskNotReadyError, match="contract version"):
        service.assert_ready(domain.id, domain.task)


@pytest.mark.asyncio
async def test_assert_ready_treats_missing_contract_version_as_stale(lab, tmp_path):
    """Tasks frozen before this change have no contract_version key — treat as stale."""
    domain = _domain(tmp_path)
    Path(domain.workspace.path).mkdir(parents=True, exist_ok=True)
    await lab.domain_store.save(domain)

    service = TaskService(lab)
    await service.create(domain.id, task_type=TaskType.REGRESSION)
    domain = await lab.domain_store.load(domain.id)
    domain.task.tools = [
        DomainTool(name="load_data", module_filename="load_data.py", code="x"),
        DomainTool(name="evaluate", module_filename="evaluate.py", code="x"),
    ]
    await lab.domain_store.save(domain)
    await service.freeze(domain.id, skip_verification=True)

    domain = await lab.domain_store.load(domain.id)
    domain.task.config.pop("contract_version", None)
    await lab.domain_store.save(domain)

    with pytest.raises(TaskNotReadyError, match="contract version"):
        service.assert_ready(domain.id, domain.task)
```

- [ ] **Step 2: Run tests to verify they fail**

```
uv run pytest tests/integration/test_task_contract_version.py -v
```
Expected: 3 FAILs — no `contract_version` stamping or check exists.

- [ ] **Step 3: Stamp `contract_version` on freeze**

In [src/dojo/runtime/task_service.py](src/dojo/runtime/task_service.py), inside `freeze`, find the block (around lines 134-138):

```python
        hashes = self._copy_tools_to_canonical(domain)
        if hashes:
            domain.task.config["tool_hashes"] = hashes

        domain.task.frozen = True
```

Add `contract_version` stamping before `domain.task.frozen = True`:

```python
        hashes = self._copy_tools_to_canonical(domain)
        if hashes:
            domain.task.config["tool_hashes"] = hashes

        spec = TASK_TYPE_REGISTRY.get(domain.task.type)
        if spec is not None:
            domain.task.config["contract_version"] = spec.contract_version

        domain.task.frozen = True
```

- [ ] **Step 4: Add the stale-version check to `assert_ready`**

In `assert_ready`, after the existing `tamper` block (around line 204-209), add:

```python
        spec = TASK_TYPE_REGISTRY.get(task.type)
        if spec is not None:
            stored = task.config.get("contract_version")
            if stored != spec.contract_version:
                raise TaskNotReadyError(
                    f"Domain {domain_id!r} task was frozen against "
                    f"contract version {stored!r}, but the current contract is "
                    f"version {spec.contract_version}. Re-verify and re-freeze: "
                    f"`dojo task generate` then `dojo task freeze`."
                )
```

- [ ] **Step 5: Bump regression `contract_version` to 2**

In [src/dojo/core/task.py](src/dojo/core/task.py), in the regression entry of `TASK_TYPE_REGISTRY`, change:

```python
        contract_version=1,
```

to:

```python
        contract_version=2,
```

This invalidates any task frozen before this change (they have version 1 or no key).

- [ ] **Step 6: Run tests to verify they pass**

```
uv run pytest tests/integration/test_task_contract_version.py -v
```
Expected: PASS.

- [ ] **Step 7: Run full suite**

```
just test
```
Expected: PASS — but any other test that calls `assert_ready` on a task it froze in-test will pass because it freezes against the current spec, which stamps the current version.

If a test fails because it constructs a `Task` directly without going through `freeze()`, update that test to either freeze through `TaskService` or set `task.config["contract_version"] = TASK_TYPE_REGISTRY[task.type].contract_version` explicitly.

- [ ] **Step 8: Commit**

```
git add src/dojo/runtime/task_service.py src/dojo/core/task.py tests/integration/test_task_contract_version.py
git commit -m "feat(task): contract_version stamping + stale-task gate at assert_ready"
```

---

## Final verification

- [ ] **Run full test suite + lint**

```
just test && just lint
```
Expected: all green.

- [ ] **Update CLAUDE.md "Open questions / known issues"**

In [CLAUDE.md](CLAUDE.md), the "Open questions / known issues" section currently mentions Phase 3 details. Add a one-liner:

```
- **Per-run artifacts** — agent code writes into ``DOJO_ARTIFACTS_DIR`` (per-experiment); framework auto-ingests into ``ArtifactStore`` and forwards to ``TrackingConnector.log_artifact``. Path: ``.dojo/domains/{id}/runs/{eid}/artifacts/``. Recorded on ``CodeRun.artifact_paths``.
- **Task-type polymorphism** — call shape (``runner_callsite``) and verifier fixture mapping (``verifier_fixture_keys``) live on ``TaskTypeSpec``. Adding a new task type is a registry-only change. ``contract_version`` invalidates frozen tasks when contracts change.
```

Commit:

```
git add CLAUDE.md
git commit -m "docs: note per-run artifacts + task-type polymorphism in CLAUDE.md"
```

---

## Self-review checklist (run after the plan is fully drafted)

- ✅ **Spec coverage:**
  - Per-run artifacts dir → A2 (env var) + A3 (ingestion) + A4 (test) + A5 (prompt).
  - Auto-ingest via ArtifactStore + TrackingConnector → A3.
  - `CodeRun.artifact_paths` → A1.
  - Extended `evaluate` contract → C1.
  - `train(X_train, y_train, X_test)` → C2 (callsite) + C3 (prompt). No ToolContract for train (correctly so — train isn't generated).
  - Task-type-polymorphic runner → B2.
  - Task-type-polymorphic verifier → B3.
  - `runner_callsite`, `verifier_fixture_keys`, `contract_version` on `TaskTypeSpec` → B1.
  - Migration via `contract_version` → D1.
  - `_REGRESSION_PROMPT` updates for artifacts + new signatures → A5 + C3.
- ✅ **Placeholder scan:** No "TBD" / "implement later" / "similar to". All code shown explicitly.
- ✅ **Type consistency:** `runner_callsite: str`, `verifier_fixture_keys: dict[str, dict[str, str]]`, `contract_version: int` used identically in B1, B2, B3, C2, D1. Function signature `_build_fixtures(spec, tool_name, raw_outputs)` consistent. `_upstream_dep(spec, tool_name)` consistent.
- ✅ **Spec drift:** Spec said "add `log_artifact` to TrackingConnector" — corrected at top: it already exists. Spec said `tool_contracts` field — corrected to `required_tools`. Spec implied train gets a ToolContract — corrected: train's contract lives in prompt + runner callsite, not `required_tools`.
