# Pass `artifacts_dir` to `evaluate` as a parameter (drop env-var leak)

**Date:** 2026-05-05
**Status:** Approved, ready for implementation plan
**Affects:** regression task type, contract version 2 → 3

## Problem

`dojo task setup` runs the verifier against the AI-generated `evaluate.py`. PROGRAM.md instructs the LLM to write debugging artifacts to `os.environ["DOJO_ARTIFACTS_DIR"]`. The verifier never sets that env var, so verification fails with `KeyError: 'DOJO_ARTIFACTS_DIR'` whenever the model takes that hint (which it does — the gridcast example produces an evaluation-summary HTML plot).

Symptom from a real run:

```
✗ evaluate  — Evaluate regression predictions using gridcast's evaluate AP
    · evaluate raised at evaluate.py:23: 'DOJO_ARTIFACTS_DIR'
✗ task cannot be frozen — verification gate failed
```

Root cause is two-part:

1. The verifier's `sandbox.execute` call ([runtime/tool_verifier.py:79-86](../../../src/dojo/runtime/tool_verifier.py#L79-L86)) inherits only `workspace.env_vars`. It does not set `DOJO_ARTIFACTS_DIR`.
2. The deeper issue: the env var is *internal Dojo plumbing*, but PROGRAM.md ([core/task.py:133-142](../../../src/dojo/core/task.py#L133-L142)) leaks the variable name and the `os.environ[...]` access pattern into the prompt that generates frozen tools. Any AI-generated code that follows the instructions becomes coupled to a runtime env var the framework may or may not set, depending on entry point.

## Goal

AI-generated code (frozen `evaluate.py`, agent-written `train`) must never reference `DOJO_ARTIFACTS_DIR` or any other Dojo-internal env var. Artifact output is requested through the function signature.

## Design

Add `artifacts_dir: Path` as a required keyword-only parameter to the regression `evaluate` contract. Frame it in PROGRAM.md as a function parameter. The env var stays alive as a private channel between `run_experiment` and the rendered runner stub — no AI-generated code ever sees it.

### New evaluate contract

```python
def evaluate(y_pred, *, X_train, X_test, y_train, y_test, artifacts_dir) -> dict:
    # implementation may write any files into artifacts_dir, or ignore it
    return {"rmse": ..., "r2": ..., "mae": ...}
```

`artifacts_dir` is always a real, writable directory. Implementations may write or ignore.

### Where the value comes from

| Caller | Source of `artifacts_dir` |
|---|---|
| Real run (`run_experiment`) | Per-experiment dir at `.dojo/domains/{id}/runs/{eid}/artifacts/` (already created today). The runner stub reads `os.environ["DOJO_ARTIFACTS_DIR"]` and passes it as the kwarg. |
| Verifier (`verify_required_tools`) | Tempdir created under `dir_path / "artifacts"` (or sibling). Discarded with the rest of the verifier's owned dir on cleanup. |

### Files touched

1. **`src/dojo/core/task.py`**
   - `RegressionTaskSpec.tool_contracts["evaluate"]`: add `artifacts_dir` to required kwargs.
   - `RegressionTaskSpec.runner_callsite`: render the call to evaluate with `artifacts_dir=Path(os.environ["DOJO_ARTIFACTS_DIR"])`.
   - `RegressionTaskSpec.verifier_fixture_keys`: add `{"evaluate": {..., "artifacts_dir": <special key>}}` mapping. The verifier resolves this special key to a tempdir at run time (see verifier change below).
   - `RegressionTaskSpec.contract_version`: bump 2 → 3.
   - PROGRAM.md template (the prompt that generates load_data + evaluate): replace the `## Artifacts` section. New text describes `artifacts_dir` as a parameter ("if you want to save evaluation plots/diagnostics, write them under `artifacts_dir`; otherwise ignore the parameter"). No mention of `DOJO_ARTIFACTS_DIR`.

2. **`src/dojo/runtime/tool_verifier.py`**
   - Today `verifier_fixture_keys` maps `{tool_name: {param: load_data_output_key}}`. `artifacts_dir` doesn't come from `load_data`, so this mapping shape needs a small extension. Two acceptable shapes — pick one in the implementation plan:
     - **(a)** Add a sentinel value, e.g. the literal string `"__artifacts_dir__"`, that the verifier resolves at run time to a freshly-created tempdir path.
     - **(b)** Add a sibling field on `TaskTypeSpec`, e.g. `verifier_runtime_fixtures: dict[str, set[str]]` (tool → param names) that the verifier injects without going through `verifier_fixture_keys`.
   - Either way, the tempdir is created as a sub-dir of `dir_path` (so the existing `_rmtree_quiet(dir_path)` on `owns_dir` handles cleanup; no new cleanup paths).
   - The verifier subprocess script (the embedded one inside `TaskTypeSpec.verifier_script`, not the runner) must construct the `Path` and pass it as a kwarg. Adjust whatever scaffolding builds that script to import `pathlib` and create + reference the tempdir.

3. **`src/dojo/runtime/runner.py`**
   - The runner template currently imports `json, sys, traceback`. Once `runner_callsite` references `os.environ` and `Path(...)`, the template needs `os` and `pathlib.Path` available. Add the imports to the template (cleanest), or to `RegressionTaskSpec.runner_prelude` (more localised). Implementation plan picks one.

4. **`src/dojo/tools/experiments.py`**
   - No change required. `run_experiment` continues to set `DOJO_ARTIFACTS_DIR` for the runner subprocess. `_ingest_artifacts` continues to walk the dir after the run.

### Contract version bump

`Task.config["contract_version"]` is already mirrored from `TaskTypeSpec.contract_version` at freeze time. Existing tasks frozen at v2 will be rejected by `assert_ready` with the standard re-verify message — which is correct behaviour because their `evaluate.py` files were generated against the old contract and would crash when called with the new kwarg.

User-facing impact: anyone with an existing `dojo task setup`-frozen domain must re-run `dojo task setup` after upgrading. Acceptable for pre-release.

## Non-goals

- **Don't change train's signature.** `train`'s prompt does not currently leak the env var, and `train` is per-experiment code regenerated every run. If a user wants train to write artifacts later, that's a separate design.
- **Don't gate artifacts on MLflow.** `ArtifactStore` is the persistent layer; tracking is a forwarder. Current layering stays.
- **Don't change the `_ingest_artifacts` flow.** Real runs ingest artifacts the same way they do today.

## Test plan

- Unit: `tool_verifier` test that builds a regression task with an evaluate that writes a file into `artifacts_dir`, verifies the file is written and the verifier completes successfully.
- Integration / E2E: `dojo task setup` against a fixture domain whose evaluate writes an HTML plot — must freeze cleanly. Run an actual experiment and assert the file lands in `lab.artifact_store` under `experiments/{eid}/artifacts/...`.
- Existing tests: regression-task verification tests must keep passing after the contract bump (update fixtures that hard-code v2).

## Out of scope / follow-ups

- The `## Artifacts` documentation block in PROGRAM.md will get a small re-word; the broader PROGRAM.md authoring guide elsewhere is unchanged.
- Future task types (classification, time-series) will inherit the same `artifacts_dir`-as-kwarg pattern via their `TaskTypeSpec` — registry-only addition, no framework change.
