"""Unit tests for verify_required_tools (combined subprocess verifier)."""

from __future__ import annotations

from dojo.core.domain import DomainTool, ToolType
from dojo.core.task import TASK_TYPE_REGISTRY, Task, TaskType
from dojo.runtime.tool_verifier import verify_required_tools
from dojo.sandbox.local import LocalSandbox


def _module_tool(name: str, code: str, *, entrypoint: str | None = None) -> DomainTool:
    return DomainTool(
        name=name,
        description=f"{name} tool",
        type=ToolType.DATA_LOADER if name == "load_data" else ToolType.EVALUATOR,
        code=code,
        module_filename=f"{name}.py",
        entrypoint=entrypoint or name,
    )


# Contract fixtures from the registry — we test against the actual contract
# the freeze gate will use.
_REG = TASK_TYPE_REGISTRY[TaskType.REGRESSION]
_LOAD_CONTRACT = next(c for c in _REG.required_tools if c.name == "load_data")
_EVAL_CONTRACT = next(c for c in _REG.required_tools if c.name == "evaluate")


GOOD_LOAD_DATA = """\
def load_data():
    X_train = [[1.0, 2.0], [3.0, 4.0]]
    X_test = [[5.0, 6.0]]
    y_train = [1.0, 2.0]
    y_test = [3.0]
    return X_train, X_test, y_train, y_test
"""

# Returns a 3-tuple instead of 4 — wrong shape
BAD_LOAD_DATA_SHAPE = """\
def load_data():
    return [[1.0]], [[2.0]], [1.0]
"""

# Returns a dict instead of a tuple — wrong kind
BAD_LOAD_DATA_DICT = """\
def load_data():
    return {"X_train": [[1.0]], "X_test": [[2.0]], "y_train": [1.0], "y_test": [2.0]}
"""

GOOD_EVALUATE = """\
import math


def evaluate(y_pred, *, X_train, X_test, y_train, y_test, artifacts_dir):
    diffs = [a - b for a, b in zip(y_pred, y_test)]
    mse = sum(d * d for d in diffs) / len(diffs)
    mae = sum(abs(d) for d in diffs) / len(diffs)
    return {"rmse": math.sqrt(mse), "r2": 1.0, "mae": mae}
"""

# Returns wrong shape — list instead of dict
BAD_EVALUATE_SHAPE = """\
def evaluate(y_pred, *, X_train, X_test, y_train, y_test, artifacts_dir):
    return [1, 2, 3]
"""

# Crashes
BAD_EVALUATE_RAISES = """\
def evaluate(y_pred, *, X_train, X_test, y_train, y_test, artifacts_dir):
    raise RuntimeError("boom")
"""

# Missing key in returned dict
BAD_EVALUATE_MISSING_KEY = """\
def evaluate(y_pred, *, X_train, X_test, y_train, y_test, artifacts_dir):
    return {"rmse": 0.5, "r2": 0.9}  # mae missing
"""


async def test_verify_required_tools_passes_for_good_tools():
    """Both load_data and evaluate pass with well-formed implementations."""
    load = _module_tool("load_data", GOOD_LOAD_DATA)
    evaluate = _module_tool("evaluate", GOOD_EVALUATE)
    task = Task(type=TaskType.REGRESSION)

    out = await verify_required_tools(
        [load, evaluate], task, sandbox=LocalSandbox(), workspace=None
    )

    assert load.verification is not None
    assert load.verification.verified is True, load.verification.errors
    assert evaluate.verification is not None
    assert evaluate.verification.verified is True, evaluate.verification.errors
    assert len(out) == 2


async def test_verify_required_tools_skips_missing_tool():
    """Missing required tools shouldn't crash — they just stay unverified."""
    load = _module_tool("load_data", GOOD_LOAD_DATA)
    task = Task(type=TaskType.REGRESSION)
    # Only load_data provided; evaluate is absent — no crash expected.
    out = await verify_required_tools([load], task, sandbox=LocalSandbox(), workspace=None)
    assert out[0].verification is not None
    assert out[0].verification.verified is True


async def test_verify_bad_load_data_shape():
    """load_data returning a 3-tuple should fail with a shape error."""
    load = _module_tool("load_data", BAD_LOAD_DATA_SHAPE)
    evaluate = _module_tool("evaluate", GOOD_EVALUATE)
    task = Task(type=TaskType.REGRESSION)
    await verify_required_tools([load, evaluate], task, sandbox=LocalSandbox(), workspace=None)
    assert load.verification is not None
    assert not load.verification.verified
    msg = " ".join(load.verification.errors).lower()
    assert "4" in msg or "tuple" in msg or "4-tuple" in msg


async def test_verify_bad_load_data_dict():
    """load_data returning a dict should fail."""
    load = _module_tool("load_data", BAD_LOAD_DATA_DICT)
    evaluate = _module_tool("evaluate", GOOD_EVALUATE)
    task = Task(type=TaskType.REGRESSION)
    await verify_required_tools([load, evaluate], task, sandbox=LocalSandbox(), workspace=None)
    assert load.verification is not None
    assert not load.verification.verified


async def test_verify_evaluate_fails_when_load_data_fails():
    """When load_data fails, evaluate gets no result marker — should fail with clear message."""
    load = _module_tool("load_data", BAD_LOAD_DATA_SHAPE)
    evaluate = _module_tool("evaluate", GOOD_EVALUATE)
    task = Task(type=TaskType.REGRESSION)
    await verify_required_tools([load, evaluate], task, sandbox=LocalSandbox(), workspace=None)
    assert load.verification is not None and not load.verification.verified
    # evaluate should also fail (script exits after load_data failure)
    assert evaluate.verification is not None
    assert not evaluate.verification.verified


async def test_verify_evaluate_raises():
    """evaluate raising an exception should surface the error message."""
    load = _module_tool("load_data", GOOD_LOAD_DATA)
    evaluate = _module_tool("evaluate", BAD_EVALUATE_RAISES)
    task = Task(type=TaskType.REGRESSION)
    await verify_required_tools([load, evaluate], task, sandbox=LocalSandbox(), workspace=None)
    assert load.verification is not None and load.verification.verified
    assert evaluate.verification is not None
    assert not evaluate.verification.verified
    msg = " ".join(evaluate.verification.errors)
    assert "boom" in msg or "raised" in msg.lower()


async def test_verify_evaluate_missing_key():
    """evaluate returning a dict missing 'mae' should fail with a key error."""
    load = _module_tool("load_data", GOOD_LOAD_DATA)
    evaluate = _module_tool("evaluate", BAD_EVALUATE_MISSING_KEY)
    task = Task(type=TaskType.REGRESSION)
    await verify_required_tools([load, evaluate], task, sandbox=LocalSandbox(), workspace=None)
    assert evaluate.verification is not None
    assert not evaluate.verification.verified
    assert any("mae" in e for e in evaluate.verification.errors)


async def test_verify_evaluate_wrong_return_type():
    """evaluate returning a list instead of dict should fail."""
    load = _module_tool("load_data", GOOD_LOAD_DATA)
    evaluate = _module_tool("evaluate", BAD_EVALUATE_SHAPE)
    task = Task(type=TaskType.REGRESSION)
    await verify_required_tools([load, evaluate], task, sandbox=LocalSandbox(), workspace=None)
    assert evaluate.verification is not None
    assert not evaluate.verification.verified
    msg = " ".join(evaluate.verification.errors).lower()
    assert "dict" in msg


async def test_verify_empty_load_data_output():
    """Empty list returns from load_data: load_data structurally passes (4-tuple of lists),
    but evaluate fails downstream because empty arrays cause a ZeroDivisionError."""
    empty_load_data = """\
def load_data():
    return [], [], [], []
"""
    load = _module_tool("load_data", empty_load_data)
    evaluate = _module_tool("evaluate", GOOD_EVALUATE)
    task = Task(type=TaskType.REGRESSION)
    await verify_required_tools([load, evaluate], task, sandbox=LocalSandbox(), workspace=None)
    assert load.verification is not None
    assert evaluate.verification is not None
    # In the combined verifier, load_data passes structurally (valid 4-tuple).
    # evaluate crashes on empty arrays (ZeroDivisionError) — the combo must fail.
    assert not evaluate.verification.verified


async def test_verify_load_data_raises():
    """When load_data raises, the error message should include file:line."""
    raising = """\
def load_data():
    raise RuntimeError("kaboom from inside the tool")
"""
    load = _module_tool("load_data", raising)
    evaluate = _module_tool("evaluate", GOOD_EVALUATE)
    task = Task(type=TaskType.REGRESSION)
    await verify_required_tools([load, evaluate], task, sandbox=LocalSandbox(), workspace=None)
    assert load.verification is not None
    assert not load.verification.verified
    msg = " ".join(load.verification.errors)
    assert "kaboom" in msg
    assert "load_data.py:" in msg


async def test_verify_pandas_return_types():
    """Real ML pipelines return pandas DataFrames/Series; the verifier should handle them."""
    pandas_load_data = """\
import pandas as pd


def load_data():
    X_train = pd.DataFrame([[1.0, 2.0], [3.0, 4.0]], columns=["a", "b"])
    X_test = pd.DataFrame([[5.0, 6.0]], columns=["a", "b"])
    y_train = pd.Series([1.0, 2.0], name="y")
    y_test = pd.Series([3.0], name="y")
    return X_train, X_test, y_train, y_test
"""
    load = _module_tool("load_data", pandas_load_data)
    evaluate = _module_tool("evaluate", GOOD_EVALUATE)
    task = Task(type=TaskType.REGRESSION)
    await verify_required_tools([load, evaluate], task, sandbox=LocalSandbox(), workspace=None)
    assert load.verification is not None
    assert load.verification.verified is True, load.verification.errors


async def test_evaluate_can_import_load_data():
    """evaluate.py may still import load_data for backwards-compat.
    Both modules are in the same dir so the import resolves."""
    load = _module_tool("load_data", GOOD_LOAD_DATA)
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
    task = Task(type=TaskType.REGRESSION)
    await verify_required_tools(
        [load, evaluate_with_import], task, sandbox=LocalSandbox(), workspace=None
    )
    assert load.verification is not None and load.verification.verified is True
    assert evaluate_with_import.verification is not None
    assert evaluate_with_import.verification.verified is True, (
        evaluate_with_import.verification.errors
    )


async def test_verify_sample_output_populated_for_evaluate():
    """After passing verification, evaluate.verification.sample_output should
    contain at least rmse, r2, mae."""
    load = _module_tool("load_data", GOOD_LOAD_DATA)
    evaluate = _module_tool("evaluate", GOOD_EVALUATE)
    task = Task(type=TaskType.REGRESSION)
    await verify_required_tools([load, evaluate], task, sandbox=LocalSandbox(), workspace=None)
    assert evaluate.verification is not None and evaluate.verification.verified
    assert {"rmse", "r2", "mae"}.issubset(evaluate.verification.sample_output.keys())


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
