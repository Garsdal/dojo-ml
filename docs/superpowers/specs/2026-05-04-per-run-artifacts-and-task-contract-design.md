# Per-run artifacts + task-interface decoupling

**Status:** design
**Date:** 2026-05-04
**Owner:** Marcus

## Problem

Two related issues in the agent run lifecycle:

1. **Artifacts overwrite each other.** The agent's generated `evaluate` writes to a workspace-relative `artifacts/` directory. Every experiment shares the same workspace, so each run clobbers the previous run's artifacts (e.g. `evaluation_summary.html`).
2. **Agent code reloads data the framework already has.** The current regression `evaluate(y_pred)` contract forces the agent to call `load_data()` inside `evaluate` to recover `X_train, X_test, y_train, y_test`. Same applies to `train()`, which has no parameters and pulls data via `load_data` internally. Beyond the duplicated work, this prevents richer evaluation outputs (e.g. forecast plots that need `X_train`, `y_train` etc.) without further data wrangling inside the agent's code.

A third structural issue surfaces while fixing the second: the runner ([runtime/runner.py](src/dojo/runtime/runner.py)) and verifier ([runtime/tool_verifier.py](src/dojo/runtime/tool_verifier.py)) both have regression-specific call patterns hardcoded. Adding any future task type (classification, ranking, etc.) would require patching them, defeating the registry pattern.

## Scope

In scope:
- Per-run artifact directory exposed to agent code.
- Framework auto-ingests run-produced artifacts into `ArtifactStore` and forwards them to the active `TrackingConnector`.
- Extended `evaluate` and `train` contracts: agent code no longer calls `load_data` inside these tools.
- Move task-type-specific call patterns out of `runner.py` and `tool_verifier.py` into `TaskTypeSpec`.

Out of scope (deferred):
- Adding a second task type (classification, etc.). The refactor makes this a localized change later, but no second type is added speculatively.
- A `## Artifacts` section in PROGRAM.md declaring expected outputs. Useful future contract, deferred until real domains demand it.
- Splitting `train` into separate `fit` / `predict` tools. Today's `train` is effectively `fit_predict`; we keep that.

## Design

### 1. Per-run artifacts directory

**Path layout.** Mirror the existing per-experiment convention used for the train script:

```
.dojo/domains/{domain_id}/runs/{experiment_id}/artifacts/
```

One directory per `Experiment`. Multiple `run_experiment_code` calls within an experiment share the directory. Files are not namespaced per `CodeRun` — the agent is responsible for choosing filenames if it wants history within an experiment, and the latest write wins by default. This matches how the train script itself is overwritten across `run_experiment_code` calls today.

**Exposure to agent code.** The runner sets `DOJO_ARTIFACTS_DIR` in the subprocess environment before invoking `train` / `evaluate`. The directory exists before the subprocess starts (created by `run_experiment_code` in [tools/experiments.py](src/dojo/tools/experiments.py)). The agent's generated `evaluate.py` reads it via `os.environ["DOJO_ARTIFACTS_DIR"]` and writes files into it.

The `_REGRESSION_PROMPT` ([core/task.py](src/dojo/core/task.py)) is updated with a one-paragraph "Artifacts" section telling the agent:
- A per-run directory is provided via `DOJO_ARTIFACTS_DIR`.
- Use it for any plots, model files, intermediate CSVs.
- Do not write to relative `artifacts/` or other workspace paths.

**Ingestion at run end.** After the subprocess exits cleanly in `run_experiment_code`:
1. Walk `DOJO_ARTIFACTS_DIR` for all files (recursive).
2. For each file, register it via `lab.artifact_store.save(...)`. Use a key prefix like `experiments/{experiment_id}/artifacts/{relative_path}`.
3. If `lab.tracking` is `MlflowTracker`, forward each via `tracking.log_artifact(experiment_id, path)`. The `TrackingConnector` interface gets a new `log_artifact` method (no-op for `FileTracker` / `NoopTracker`, real implementation for MLflow).
4. Record artifact paths on the `CodeRun` so the API can list them. `CodeRun` gains an `artifact_paths: list[str]` field.

Failure of artifact ingestion does not fail the run — log a warning, continue. (Failure of the user's code itself still fails the run as before.)

### 2. Extended `train` and `evaluate` contracts

**New signatures (regression):**

```python
def train(X_train, y_train, X_test) -> y_pred: ...

def evaluate(y_pred, *, X_train, X_test, y_train, y_test) -> dict[str, float]: ...
```

Both keyword-only for the data params on `evaluate`; `train` keeps positional ordering for ergonomics since its three params are simple. Neither calls `load_data` internally.

**ToolContract changes** ([core/task.py](src/dojo/core/task.py)):

```python
ToolContract(
    name="train",
    params_schema={
        "X_train": "DataFrame",
        "y_train": "Series",
        "X_test": "DataFrame",
    },
    returns_schema={"y_pred": "array-like of float"},
    return_kind="array",
)

ToolContract(
    name="evaluate",
    params_schema={
        "y_pred": "array-like of float",
        "X_train": "DataFrame",
        "X_test": "DataFrame",
        "y_train": "Series",
        "y_test": "Series",
    },
    returns_schema={"rmse": "float", "r2": "float", "mae": "float"},
    return_kind="dict",
)
```

`expected_metrics` derivation in [runtime/task_service.py](src/dojo/runtime/task_service.py) is unchanged — still pulls keys from the evaluator's `returns_schema`.

**Prompt update.** `_REGRESSION_PROMPT` is rewritten so the agent:
- Implements `train(X_train, y_train, X_test)` returning predictions on `X_test`.
- Implements `evaluate(y_pred, *, X_train, X_test, y_train, y_test)` returning the metrics dict.
- Does not call `load_data` from inside either tool.
- Uses `DOJO_ARTIFACTS_DIR` for any files it produces.

### 3. Task-type-polymorphic runner + verifier

`TaskTypeSpec` ([core/task.py](src/dojo/core/task.py)) gains two new fields:

```python
@dataclass(frozen=True)
class TaskTypeSpec:
    type: TaskType
    system_prompt: str
    tool_contracts: list[ToolContract]
    runner_callsite: str                          # rendered into the runner script
    verifier_fixture_keys: dict[str, dict[str, str]]   # tool_name -> {param_name: load_data_key}
```

For regression:

```python
runner_callsite = (
    "y_pred = train(X_train, y_train, X_test)\n"
    "metrics = evaluate(y_pred, X_train=X_train, X_test=X_test, y_train=y_train, y_test=y_test)"
)

verifier_fixture_keys = {
    "train": {"X_train": "X_train", "y_train": "y_train", "X_test": "X_test"},
    "evaluate": {
        "y_pred": "y_test",   # placeholder for verification: use y_test as a stand-in
        "X_train": "X_train",
        "X_test": "X_test",
        "y_train": "y_train",
        "y_test": "y_test",
    },
}
```

`render_runner` in [runtime/runner.py](src/dojo/runtime/runner.py) becomes task-type-agnostic: it looks up `runner_callsite` from the spec and inlines it. The runner template is responsible for unpacking `load_data()` into `X_train, X_test, y_train, y_test` (this is a stable framework-level convention, not a task-type detail) and printing the `__DOJO_METRICS__` marker.

`_build_fixtures` in [runtime/tool_verifier.py](src/dojo/runtime/tool_verifier.py) becomes task-type-agnostic: for each tool it's verifying, it looks up `verifier_fixture_keys[tool_name]` and maps `load_data` outputs into the contract params.

After this refactor, adding a future task type means: define `TaskTypeSpec.system_prompt`, `tool_contracts`, `runner_callsite`, `verifier_fixture_keys`, register in `TASK_TYPE_REGISTRY`. No changes to `runner.py` or `tool_verifier.py`.

## Data model changes

**`CodeRun`** ([core/experiment.py](src/dojo/core/experiment.py)) gains:

```python
artifact_paths: list[str] = field(default_factory=list)
```

Populated post-run with paths registered into `ArtifactStore`. Existing serialized `CodeRun` records load with an empty list (default).

**`TrackingConnector`** ([interfaces/tracking.py](src/dojo/interfaces/tracking.py)) gains:

```python
async def log_artifact(self, experiment_id: str, path: str) -> None: ...
```

`NoopTracker` and `FileTracker` no-op. `MlflowTracker` forwards to `mlflow.log_artifact` under the appropriate run.

**`TaskTypeSpec`** gains:
- `runner_callsite: str` — required.
- `verifier_fixture_keys: dict[str, dict[str, str]]` — required.
- `contract_version: int` — required. Bumped whenever any `tool_contracts` entry changes. Mirrored onto each persisted `Task` at freeze time so `assert_ready` can detect stale verifications (see Migration).

All three populated in the regression entry of `TASK_TYPE_REGISTRY`.

## Migration

`Domain.task` records are persisted as JSON in `.dojo/`. Existing tasks were frozen against the old contract (single-param `evaluate`). On load:
- Old `Task.config["expected_metrics"]` is unaffected (same metric keys).
- Old verification status (`verified=True`) is **invalidated** for any existing tool whose contract changed. The cleanest path: bump a `contract_version` field on `TaskTypeSpec`, and `task_service.assert_ready` rejects tasks whose stored verification was against an older version. The user re-runs `dojo task generate` (or whatever the current re-verification entrypoint is) once.

This is a one-time migration cost. Given Dojo is single-tenant and pre-1.0, asking the user to re-verify their domain's tools is acceptable. Document it in the changelog.

## Testing

- **Unit:** `_build_fixtures` correctly maps `load_data` outputs to contract params for the new evaluate signature. `render_runner` produces the new callsite. New `CodeRun.artifact_paths` round-trips through serialization.
- **Integration:** End-to-end `run_experiment_code` produces files in `DOJO_ARTIFACTS_DIR`, framework registers them via `ArtifactStore`, `CodeRun.artifact_paths` reflects them.
- **Verifier:** Tool verifier successfully verifies a stub `evaluate` matching the new signature; rejects one matching the old (single-param) signature.
- **MLflow path:** With `MlflowTracker` configured, artifacts produced by a run land in the MLflow run's artifact store.
- **Regression prompt:** A stub agent run end-to-end completes with the new prompt and produces metrics + at least one artifact.

## Open questions

- **Artifact ingestion ordering vs. metric extraction.** `run_experiment_code` parses `__DOJO_METRICS__` from stdout and ingests artifacts from the directory. These are independent — fine to do both unconditionally, but if the run errored mid-way with partial artifacts written, do we still ingest them? Proposed: yes, ingest whatever exists; this is debugging value when a run fails partway.
- **Per-CodeRun vs per-Experiment artifacts.** Picked per-Experiment for simplicity. If history within an experiment turns out to matter (e.g. comparing successive `run_experiment_code` calls), revisit by adding a `{run_number}/` subdirectory layer.
