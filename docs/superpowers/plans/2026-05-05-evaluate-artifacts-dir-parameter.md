# Pass `artifacts_dir` to `evaluate` as a Parameter — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the `DOJO_ARTIFACTS_DIR` env-var convention in AI-generated `evaluate.py` with an explicit `artifacts_dir: Path` parameter so neither the LLM nor the verifier ever needs to know about the env var.

**Architecture:** Three sites change in `core/task.py` (verifier script, runner callsite, generation prompt + ToolContract + contract_version) and one in `runner.py` (add `os`/`Path` imports to the template). The env var continues to exist as private plumbing between `run_experiment` and the runner subprocess — invisible to generated code. Contract version bumps 2 → 3; existing frozen tasks must re-verify.

**Tech Stack:** Python 3.13, pytest (asyncio_mode=auto), `just test` to run the suite.

---

## File Map

| File | Change |
|---|---|
| `src/dojo/core/task.py` | (1) `_REGRESSION_VERIFIER` — pass `artifacts_dir` kwarg to evaluate call. (2) `_REGRESSION_PROMPT` — drop `## Artifacts` env-var section, add `artifacts_dir` to Module 2 signature. (3) `runner_callsite` — add `artifacts_dir=Path(os.environ["DOJO_ARTIFACTS_DIR"])`. (4) evaluate `ToolContract.params_schema` — add `"artifacts_dir"` key. (5) `contract_version` — bump 2 → 3. |
| `src/dojo/runtime/runner.py` | Add `import os` and `from pathlib import Path` to the rendered runner template. |
| `tests/unit/test_tool_verifier.py` | Update all evaluate fixture functions to accept `artifacts_dir` kwarg. Add test that evaluate writing a file into `artifacts_dir` passes verification. |
| `tests/unit/test_task_type_spec_fields.py` | Update signature/callsite/schema assertions to match new contract. |

No other files change. `tools/experiments.py` keeps setting `DOJO_ARTIFACTS_DIR` for the runner subprocess unchanged.

---

## Task 1: Verifier script passes `artifacts_dir` to evaluate

**Files:**
- Modify: `tests/unit/test_tool_verifier.py`
- Modify: `src/dojo/core/task.py` (only `_REGRESSION_VERIFIER` string, lines 199-279)

- [ ] **Step 1: Write the new failing test**

In `tests/unit/test_tool_verifier.py`, add this test at the bottom (before the last test to keep grouping sensible):

```python
async def test_evaluate_receives_artifacts_dir():
    """evaluate with artifacts_dir in its signature must verify successfully,
    and writing a file into artifacts_dir must not crash verification."""
    load = _module_tool("load_data", GOOD_LOAD_DATA)
    evaluate_writes = _module_tool(
        "evaluate",
        """\
import math


def evaluate(y_pred, *, X_train, X_test, y_train, y_test, artifacts_dir):
    (artifacts_dir / "summary.txt").write_text("ok")
    diffs = [a - b for a, b in zip(y_pred, y_test)]
    mse = sum(d * d for d in diffs) / len(diffs)
    mae = sum(abs(d) for d in diffs) / len(diffs)
    return {"rmse": math.sqrt(mse), "r2": 1.0, "mae": mae}
""",
    )
    task = Task(type=TaskType.REGRESSION)
    await verify_required_tools(
        [load, evaluate_writes], task, sandbox=LocalSandbox(), workspace=None
    )
    assert evaluate_writes.verification is not None
    assert evaluate_writes.verification.verified is True, evaluate_writes.verification.errors
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd /Users/marcusgarsdal/Personal/Dojo && uv run pytest tests/unit/test_tool_verifier.py::test_evaluate_receives_artifacts_dir -v
```

Expected: FAIL — `TypeError: evaluate() got an unexpected keyword argument 'artifacts_dir'` (the verifier script doesn't pass it yet).

- [ ] **Step 3: Update `_REGRESSION_VERIFIER` in `src/dojo/core/task.py`**

Find the `# ── Step 2: evaluate` block inside the `_REGRESSION_VERIFIER` string (around line 261). Replace just the evaluate call section:

Old:
```python
# ── Step 2: evaluate ─────────────────────────────────────────────────────────

try:
    from evaluate import evaluate as _evaluate
    _metrics = _evaluate(y_test, X_train=X_train, X_test=X_test, y_train=y_train, y_test=y_test)
```

New:
```python
# ── Step 2: evaluate ─────────────────────────────────────────────────────────

try:
    from evaluate import evaluate as _evaluate
    _artifacts_dir = _HERE / "artifacts"
    _artifacts_dir.mkdir(exist_ok=True)
    _metrics = _evaluate(y_test, X_train=X_train, X_test=X_test, y_train=y_train, y_test=y_test, artifacts_dir=_artifacts_dir)
```

`_HERE` is already defined at the top of the verifier script as `Path(__file__).parent`. The directory is inside the managed temp dir that `verify_required_tools` cleans up via `_rmtree_quiet` — no separate cleanup needed.

- [ ] **Step 4: Run to confirm new test passes**

```bash
cd /Users/marcusgarsdal/Personal/Dojo && uv run pytest tests/unit/test_tool_verifier.py::test_evaluate_receives_artifacts_dir -v
```

Expected: PASS.

- [ ] **Step 5: Update existing evaluate fixtures to accept `artifacts_dir`**

In `tests/unit/test_tool_verifier.py`, update these module-level fixtures so they match the new contract. The existing tests will continue to pass — evaluate now *receives* the kwarg rather than missing it.

Replace `GOOD_EVALUATE`:
```python
GOOD_EVALUATE = """\
import math


def evaluate(y_pred, *, X_train, X_test, y_train, y_test, artifacts_dir):
    diffs = [a - b for a, b in zip(y_pred, y_test)]
    mse = sum(d * d for d in diffs) / len(diffs)
    mae = sum(abs(d) for d in diffs) / len(diffs)
    return {"rmse": math.sqrt(mse), "r2": 1.0, "mae": mae}
"""
```

Replace `BAD_EVALUATE_SHAPE`:
```python
BAD_EVALUATE_SHAPE = """\
def evaluate(y_pred, *, X_train, X_test, y_train, y_test, artifacts_dir):
    return [1, 2, 3]
"""
```

Replace `BAD_EVALUATE_RAISES`:
```python
BAD_EVALUATE_RAISES = """\
def evaluate(y_pred, *, X_train, X_test, y_train, y_test, artifacts_dir):
    raise RuntimeError("boom")
"""
```

Replace `BAD_EVALUATE_MISSING_KEY`:
```python
BAD_EVALUATE_MISSING_KEY = """\
def evaluate(y_pred, *, X_train, X_test, y_train, y_test, artifacts_dir):
    return {"rmse": 0.5, "r2": 0.9}  # mae missing
"""
```

Also update the inline evaluate inside `test_evaluate_can_import_load_data` (around line 237):

Old:
```python
    evaluate_with_import = _module_tool(
        "evaluate",
        """\
import math
from load_data import load_data


def evaluate(y_pred, *, X_train, X_test, y_train, y_test):
    diffs = [a - b for a, b in zip(y_pred, y_test)]
    mse = sum(d * d for d in diffs) / len(diffs)
    mae = sum(abs(d) for d in diffs) / len(diffs)
    return {"rmse": math.sqrt(mse), "r2": 1.0, "mae": mae}
""",
    )
```

New:
```python
    evaluate_with_import = _module_tool(
        "evaluate",
        """\
import math
from load_data import load_data


def evaluate(y_pred, *, X_train, X_test, y_train, y_test, artifacts_dir):
    diffs = [a - b for a, b in zip(y_pred, y_test)]
    mse = sum(d * d for d in diffs) / len(diffs)
    mae = sum(abs(d) for d in diffs) / len(diffs)
    return {"rmse": math.sqrt(mse), "r2": 1.0, "mae": mae}
""",
    )
```

- [ ] **Step 6: Run all verifier unit tests**

```bash
cd /Users/marcusgarsdal/Personal/Dojo && uv run pytest tests/unit/test_tool_verifier.py -v
```

Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
cd /Users/marcusgarsdal/Personal/Dojo && git add src/dojo/core/task.py tests/unit/test_tool_verifier.py
git commit -m "feat(verifier): pass artifacts_dir to evaluate during verification"
```

---

## Task 2: Update runner callsite and template imports

**Files:**
- Modify: `src/dojo/runtime/runner.py`
- Modify: `src/dojo/core/task.py` (only `runner_callsite` field, around line 333)
- Modify: `tests/unit/test_task_type_spec_fields.py`

- [ ] **Step 1: Write the failing test**

In `tests/unit/test_task_type_spec_fields.py`, update `test_regression_runner_callsite_passes_data_to_train_and_evaluate` (currently around line 25):

Old:
```python
def test_regression_runner_callsite_passes_data_to_train_and_evaluate():
    spec = TASK_TYPE_REGISTRY[TaskType.REGRESSION]
    callsite = spec.runner_callsite
    assert "train(X_train, y_train, X_test)" in callsite
    assert "X_train=X_train" in callsite
    assert "y_test=y_test" in callsite
```

New:
```python
def test_regression_runner_callsite_passes_data_to_train_and_evaluate():
    spec = TASK_TYPE_REGISTRY[TaskType.REGRESSION]
    callsite = spec.runner_callsite
    assert "train(X_train, y_train, X_test)" in callsite
    assert "X_train=X_train" in callsite
    assert "y_test=y_test" in callsite
    assert "artifacts_dir=" in callsite
    assert "DOJO_ARTIFACTS_DIR" in callsite
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd /Users/marcusgarsdal/Personal/Dojo && uv run pytest tests/unit/test_task_type_spec_fields.py::test_regression_runner_callsite_passes_data_to_train_and_evaluate -v
```

Expected: FAIL — `AssertionError` on `"artifacts_dir=" in callsite`.

- [ ] **Step 3: Update `runner_callsite` in `src/dojo/core/task.py`**

Find the `runner_callsite=` field in `TASK_TYPE_REGISTRY` (around line 333). Replace it:

Old:
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
```

New:
```python
        runner_callsite=(
            "y_pred = train(X_train, y_train, X_test)\n"
            "    metrics = evaluate("
            "y_pred, "
            "X_train=X_train, "
            "X_test=X_test, "
            "y_train=y_train, "
            "y_test=y_test, "
            'artifacts_dir=Path(os.environ["DOJO_ARTIFACTS_DIR"]))'
        ),
```

- [ ] **Step 4: Add `os` and `Path` to the runner template in `src/dojo/runtime/runner.py`**

Find the f-string in `render_runner` (around line 61). Change the first import line:

Old:
```python
    return f"""\
import json, sys, traceback
```

New:
```python
    return f"""\
import json, os, sys, traceback
from pathlib import Path
```

- [ ] **Step 5: Run callsite test + full runner test suite**

```bash
cd /Users/marcusgarsdal/Personal/Dojo && uv run pytest tests/unit/test_task_type_spec_fields.py::test_regression_runner_callsite_passes_data_to_train_and_evaluate tests/unit/test_runner.py -v
```

Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
cd /Users/marcusgarsdal/Personal/Dojo && git add src/dojo/core/task.py src/dojo/runtime/runner.py tests/unit/test_task_type_spec_fields.py
git commit -m "feat(runner): pass artifacts_dir to evaluate via callsite; add os/Path imports to runner template"
```

---

## Task 3: Update `_REGRESSION_PROMPT` — drop env-var section, add `artifacts_dir` to signature

**Files:**
- Modify: `src/dojo/core/task.py` (only `_REGRESSION_PROMPT` string, around lines 94-197)
- Modify: `tests/unit/test_task_type_spec_fields.py`

- [ ] **Step 1: Write the failing test**

In `tests/unit/test_task_type_spec_fields.py`, update `test_regression_prompt_specifies_new_evaluate_signature` (around line 33):

Old:
```python
def test_regression_prompt_specifies_new_evaluate_signature():
    spec = TASK_TYPE_REGISTRY[TaskType.REGRESSION]
    prompt = spec.generation_prompt_template
    assert "def evaluate(y_pred, *, X_train, X_test, y_train, y_test)" in prompt
    assert "def evaluate(y_pred):" not in prompt
```

New:
```python
def test_regression_prompt_specifies_new_evaluate_signature():
    spec = TASK_TYPE_REGISTRY[TaskType.REGRESSION]
    prompt = spec.generation_prompt_template
    assert "def evaluate(y_pred, *, X_train, X_test, y_train, y_test, artifacts_dir)" in prompt
    assert "DOJO_ARTIFACTS_DIR" not in prompt
    assert "os.environ" not in prompt
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd /Users/marcusgarsdal/Personal/Dojo && uv run pytest tests/unit/test_task_type_spec_fields.py::test_regression_prompt_specifies_new_evaluate_signature -v
```

Expected: FAIL on the `artifacts_dir` assertion (and possibly the `DOJO_ARTIFACTS_DIR` assertion).

- [ ] **Step 3: Update `_REGRESSION_PROMPT` in `src/dojo/core/task.py`**

Make two edits to the `_REGRESSION_PROMPT` string:

**Edit A** — Remove the entire `## Artifacts` block and replace with nothing. Find and delete these lines (around line 133-142):

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

**Edit B** — Update Module 2 description. Find this block (around lines 160-169):

Old:
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
```

New:
```
Module 2 — evaluate.py
- Defines a top-level function:
  `def evaluate(y_pred, *, X_train, X_test, y_train, y_test, artifacts_dir) -> dict`.
- Receives all data splits and an ``artifacts_dir: Path`` as parameters.
  Do **not** call ``load_data`` inside ``evaluate``. The framework loads
  data once and passes the splits in.
- Computes: rmse (float), r2 (float), mae (float) against ``y_test``.
- Returns a dict with exactly those three keys: {{"rmse": ..., "r2": ..., "mae": ...}}.
- Must NOT print to stdout — return only.
- May write evaluation plots or diagnostics into ``artifacts_dir`` (a
  real, writable directory — write files there directly). This is optional;
  ignore the parameter if you have nothing to save.
```

Also update the signature hint inside `## How to read this` (around line 115-117):

Old:
```
    - `## Evaluate` ⟶ steers what goes *inside* `evaluate.py`. Read this before
      writing module 2. (The signature is
      `def evaluate(y_pred, *, X_train, X_test, y_train, y_test)` returning
      `{{"rmse", "r2", "mae"}}` — only the body is yours to shape.)
```

New:
```
    - `## Evaluate` ⟶ steers what goes *inside* `evaluate.py`. Read this before
      writing module 2. (The signature is
      `def evaluate(y_pred, *, X_train, X_test, y_train, y_test, artifacts_dir)`
      returning `{{"rmse", "r2", "mae"}}` — only the body is yours to shape.)
```

- [ ] **Step 4: Run the prompt test**

```bash
cd /Users/marcusgarsdal/Personal/Dojo && uv run pytest tests/unit/test_task_type_spec_fields.py::test_regression_prompt_specifies_new_evaluate_signature -v
```

Expected: PASS.

- [ ] **Step 5: Run full spec-fields suite**

```bash
cd /Users/marcusgarsdal/Personal/Dojo && uv run pytest tests/unit/test_task_type_spec_fields.py -v
```

Expected: all PASS. (The regression prompt test in `test_regression_prompt.py` may need checking — run it too if it exists.)

```bash
cd /Users/marcusgarsdal/Personal/Dojo && uv run pytest tests/unit/test_regression_prompt.py -v
```

If any test asserts the old signature string (`def evaluate(y_pred, *, X_train, X_test, y_train, y_test)` without `artifacts_dir`), update it to check for the new signature.

- [ ] **Step 6: Commit**

```bash
cd /Users/marcusgarsdal/Personal/Dojo && git add src/dojo/core/task.py tests/unit/test_task_type_spec_fields.py tests/unit/test_regression_prompt.py
git commit -m "feat(prompt): replace DOJO_ARTIFACTS_DIR with artifacts_dir parameter in evaluate contract"
```

---

## Task 4: Update `evaluate` ToolContract params_schema and bump `contract_version`

**Files:**
- Modify: `src/dojo/core/task.py` (ToolContract params_schema + contract_version, around lines 309-348)
- Modify: `tests/unit/test_task_type_spec_fields.py`

- [ ] **Step 1: Write the failing tests**

In `tests/unit/test_task_type_spec_fields.py`, update `test_regression_evaluate_contract_includes_train_test_splits` and add a version test:

Old:
```python
def test_regression_evaluate_contract_includes_train_test_splits():
    spec = TASK_TYPE_REGISTRY[TaskType.REGRESSION]
    evaluate = next(c for c in spec.required_tools if c.name == "evaluate")
    for key in ["y_pred", "X_train", "X_test", "y_train", "y_test"]:
        assert key in evaluate.params_schema, evaluate.params_schema
```

New:
```python
def test_regression_evaluate_contract_includes_train_test_splits():
    spec = TASK_TYPE_REGISTRY[TaskType.REGRESSION]
    evaluate = next(c for c in spec.required_tools if c.name == "evaluate")
    for key in ["y_pred", "X_train", "X_test", "y_train", "y_test", "artifacts_dir"]:
        assert key in evaluate.params_schema, evaluate.params_schema


def test_regression_contract_version_is_at_least_3():
    spec = TASK_TYPE_REGISTRY[TaskType.REGRESSION]
    assert spec.contract_version >= 3
```

- [ ] **Step 2: Run to confirm failures**

```bash
cd /Users/marcusgarsdal/Personal/Dojo && uv run pytest tests/unit/test_task_type_spec_fields.py::test_regression_evaluate_contract_includes_train_test_splits tests/unit/test_task_type_spec_fields.py::test_regression_contract_version_is_at_least_3 -v
```

Expected: both FAIL.

- [ ] **Step 3: Update the `evaluate` ToolContract `params_schema` in `src/dojo/core/task.py`**

Find the `evaluate` ToolContract inside `TASK_TYPE_REGISTRY` (around line 309). Add `"artifacts_dir"` to its `params_schema`:

Old:
```python
                params_schema={
                    "y_pred": "list of float",
                    "X_train": "list of lists (float)",
                    "X_test": "list of lists (float)",
                    "y_train": "list of float",
                    "y_test": "list of float",
                },
```

New:
```python
                params_schema={
                    "y_pred": "list of float",
                    "X_train": "list of lists (float)",
                    "X_test": "list of lists (float)",
                    "y_train": "list of float",
                    "y_test": "list of float",
                    "artifacts_dir": "Path",
                },
```

- [ ] **Step 4: Bump `contract_version` in `src/dojo/core/task.py`**

Find `contract_version=2` (around line 347). Change to:

```python
        contract_version=3,
```

- [ ] **Step 5: Run the two new tests**

```bash
cd /Users/marcusgarsdal/Personal/Dojo && uv run pytest tests/unit/test_task_type_spec_fields.py::test_regression_evaluate_contract_includes_train_test_splits tests/unit/test_task_type_spec_fields.py::test_regression_contract_version_is_at_least_3 -v
```

Expected: both PASS.

- [ ] **Step 6: Run full unit suite**

```bash
cd /Users/marcusgarsdal/Personal/Dojo && uv run pytest tests/unit/ -v
```

Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
cd /Users/marcusgarsdal/Personal/Dojo && git add src/dojo/core/task.py tests/unit/test_task_type_spec_fields.py
git commit -m "feat(task): add artifacts_dir to evaluate ToolContract params_schema; bump contract_version to 3"
```

---

## Task 5: Final integration check

- [ ] **Step 1: Run the full test suite**

```bash
cd /Users/marcusgarsdal/Personal/Dojo && just test
```

Expected: all PASS. If integration or e2e tests fail referencing `contract_version == 2`, update any hard-coded version assertions to `>= 3`.

- [ ] **Step 2: Run lint**

```bash
cd /Users/marcusgarsdal/Personal/Dojo && just lint
```

Expected: no errors. If any, run `just format` and re-check.

- [ ] **Step 3: Commit any fixups**

Only needed if step 1 or 2 found issues. Use:

```bash
git add <files>
git commit -m "fix: update contract_version assertions and lint after v3 bump"
```

- [ ] **Step 4: Verify the bug is gone manually (optional)**

If you have a gridcast domain with a frozen task, re-run `dojo task setup` to regenerate with the new prompt. The new `evaluate.py` should define `def evaluate(y_pred, *, ..., artifacts_dir)` and pass verification cleanly.
