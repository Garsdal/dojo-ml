"""Unit tests for ToolVerifier (Phase 4 — import-based)."""

from __future__ import annotations

from dojo.core.domain import DomainTool, ToolType
from dojo.core.task import TASK_TYPE_REGISTRY, Task, TaskType, ToolContract
from dojo.runtime.tool_verifier import ToolVerifier, verify_required_tools
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


def evaluate(y_pred, *, X_train, X_test, y_train, y_test):
    diffs = [a - b for a, b in zip(y_pred, y_test)]
    mse = sum(d * d for d in diffs) / len(diffs)
    mae = sum(abs(d) for d in diffs) / len(diffs)
    return {"rmse": math.sqrt(mse), "r2": 1.0, "mae": mae}
"""

# Returns wrong shape — list instead of dict
BAD_EVALUATE_SHAPE = """\
def evaluate(y_pred, *, X_train, X_test, y_train, y_test):
    return [1, 2, 3]
"""

# Crashes
BAD_EVALUATE_RAISES = """\
def evaluate(y_pred, *, X_train, X_test, y_train, y_test):
    raise RuntimeError("boom")
"""

# Module exists but is missing the entrypoint function
NO_ENTRYPOINT = """\
def something_else():
    return {"rmse": 0.0, "r2": 0.0, "mae": 0.0}
"""

# Missing key in returned dict
BAD_EVALUATE_MISSING_KEY = """\
def evaluate(y_pred, *, X_train, X_test, y_train, y_test):
    return {"rmse": 0.5, "r2": 0.9}  # mae missing
"""


async def test_verifier_passes_for_good_load_data():
    tool = _module_tool("load_data", GOOD_LOAD_DATA)
    v = ToolVerifier(LocalSandbox())
    result = await v.verify(tool, _LOAD_CONTRACT, workspace=None)
    assert result.verified is True, result.errors
    assert result.errors == []
    assert "X_train" in result.sample_output
    assert result.sample_output["X_train"]["length"] == 2


async def test_verifier_flags_wrong_tuple_length():
    tool = _module_tool("load_data", BAD_LOAD_DATA_SHAPE)
    v = ToolVerifier(LocalSandbox())
    result = await v.verify(tool, _LOAD_CONTRACT, workspace=None)
    assert result.verified is False
    assert any("3 items" in e or "expected 4" in e for e in result.errors)


async def test_verifier_flags_wrong_return_kind():
    tool = _module_tool("load_data", BAD_LOAD_DATA_DICT)
    v = ToolVerifier(LocalSandbox())
    result = await v.verify(tool, _LOAD_CONTRACT, workspace=None)
    assert result.verified is False
    assert any("tuple" in e for e in result.errors)


async def test_verifier_passes_for_good_evaluate_with_fixture():
    tool = _module_tool("evaluate", GOOD_EVALUATE)
    v = ToolVerifier(LocalSandbox())
    result = await v.verify(
        tool,
        _EVAL_CONTRACT,
        workspace=None,
        fixtures={
            "y_pred": [1.0, 2.0, 3.0],
            "X_train": [[1.0]],
            "X_test": [[2.0]],
            "y_train": [1.0],
            "y_test": [1.0, 2.0, 3.0],
        },
    )
    assert result.verified is True, result.errors
    assert {"rmse", "r2", "mae"}.issubset(result.sample_output.keys())


async def test_verifier_requires_fixture_when_contract_has_params():
    tool = _module_tool("evaluate", GOOD_EVALUATE)
    v = ToolVerifier(LocalSandbox())
    result = await v.verify(tool, _EVAL_CONTRACT, workspace=None)
    assert result.verified is False
    assert any("y_pred" in e for e in result.errors)


_EVAL_FIXTURES = {
    "y_pred": [1.0],
    "X_train": [[1.0]],
    "X_test": [[1.0]],
    "y_train": [1.0],
    "y_test": [1.0],
}


async def test_verifier_catches_crashes():
    tool = _module_tool("evaluate", BAD_EVALUATE_RAISES)
    v = ToolVerifier(LocalSandbox())
    result = await v.verify(tool, _EVAL_CONTRACT, workspace=None, fixtures=_EVAL_FIXTURES)
    assert result.verified is False
    assert any("boom" in e or "raised" in e.lower() for e in result.errors)


async def test_verifier_rejects_non_dict_evaluate():
    tool = _module_tool("evaluate", BAD_EVALUATE_SHAPE)
    v = ToolVerifier(LocalSandbox())
    result = await v.verify(tool, _EVAL_CONTRACT, workspace=None, fixtures=_EVAL_FIXTURES)
    assert result.verified is False
    assert any("dict" in e for e in result.errors)


async def test_verifier_rejects_missing_key():
    tool = _module_tool("evaluate", BAD_EVALUATE_MISSING_KEY)
    v = ToolVerifier(LocalSandbox())
    result = await v.verify(tool, _EVAL_CONTRACT, workspace=None, fixtures=_EVAL_FIXTURES)
    assert result.verified is False
    assert any("mae" in e for e in result.errors)


async def test_verifier_rejects_missing_entrypoint():
    tool = _module_tool("evaluate", NO_ENTRYPOINT)
    v = ToolVerifier(LocalSandbox())
    result = await v.verify(tool, _EVAL_CONTRACT, workspace=None, fixtures=_EVAL_FIXTURES)
    assert result.verified is False
    assert any("evaluate" in e for e in result.errors)


async def test_verifier_rejects_empty_code():
    tool = _module_tool("load_data", "")
    v = ToolVerifier(LocalSandbox())
    result = await v.verify(tool, _LOAD_CONTRACT, workspace=None)
    assert result.verified is False
    assert any("no code" in e.lower() for e in result.errors)


async def test_verify_required_tools_threads_y_test_into_evaluate():
    load = _module_tool("load_data", GOOD_LOAD_DATA)
    evaluate = _module_tool("evaluate", GOOD_EVALUATE)
    task = Task(type=TaskType.REGRESSION)

    out = await verify_required_tools(
        [load, evaluate], task, sandbox=LocalSandbox(), workspace=None
    )

    assert load.verification is not None
    assert load.verification.verified is True
    assert evaluate.verification is not None
    assert evaluate.verification.verified is True, evaluate.verification.errors
    assert len(out) == 2


async def test_verify_required_tools_skips_missing_tool():
    """Missing required tools shouldn't crash — they just stay unverified."""
    load = _module_tool("load_data", GOOD_LOAD_DATA)
    task = Task(type=TaskType.REGRESSION)
    out = await verify_required_tools([load], task, sandbox=LocalSandbox(), workspace=None)
    assert out[0].verification is not None
    assert out[0].verification.verified is True


async def test_verify_required_tools_evaluate_fails_when_load_data_fails():
    load = _module_tool("load_data", BAD_LOAD_DATA_SHAPE)
    evaluate = _module_tool("evaluate", GOOD_EVALUATE)
    task = Task(type=TaskType.REGRESSION)
    await verify_required_tools([load, evaluate], task, sandbox=LocalSandbox(), workspace=None)
    assert load.verification is not None and not load.verification.verified
    # When load_data fails, evaluate is *skipped* with a clear cascade message
    # rather than the misleading "missing fixture for parameter 'y_pred'".
    assert evaluate.verification is not None
    assert not evaluate.verification.verified
    msg = " ".join(evaluate.verification.errors).lower()
    assert "skipped" in msg
    assert "load_data" in msg


async def test_evaluate_can_import_load_data():
    """Phase 4 contract: ``evaluate.py`` may still import ``load_data`` for
    backwards-compat (e.g. to load extra context). The verifier must lay both
    modules in the same dir so the import resolves."""
    load = _module_tool("load_data", GOOD_LOAD_DATA)
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
    task = Task(type=TaskType.REGRESSION)
    await verify_required_tools(
        [load, evaluate_with_import], task, sandbox=LocalSandbox(), workspace=None
    )
    assert load.verification is not None and load.verification.verified is True
    assert evaluate_with_import.verification is not None
    assert evaluate_with_import.verification.verified is True, (
        evaluate_with_import.verification.errors
    )


async def test_verifier_rejects_empty_load_data_output():
    """Empty list returns used to pass the type check ('list of float' was
    satisfied by []) and produced misleading downstream sklearn errors. They
    should now fail at load_data with an actionable message about the dataset
    window."""
    empty_load_data = """\
def load_data():
    return [], [], [], []
"""
    tool = _module_tool("load_data", empty_load_data)
    v = ToolVerifier(LocalSandbox())
    result = await v.verify(tool, _LOAD_CONTRACT, workspace=None)
    assert result.verified is False
    msg = " ".join(result.errors).lower()
    assert "non-empty" in msg or "0 rows" in msg
    assert "program.md" in msg


async def test_verifier_surfaces_traceback_file_line():
    """When a tool raises, the error message should include the user-code
    file:line so the user knows where to look."""
    raising = """\
def load_data():
    raise RuntimeError("kaboom from inside the tool")
"""
    tool = _module_tool("load_data", raising)
    v = ToolVerifier(LocalSandbox())
    result = await v.verify(tool, _LOAD_CONTRACT, workspace=None)
    assert result.verified is False
    msg = " ".join(result.errors)
    assert "load_data.py:" in msg
    assert "kaboom" in msg


async def test_verifier_accepts_pandas_return_types():
    """Real ML pipelines return pandas DataFrames/Series. The verifier's JSON
    encoder used to silently `str()` DataFrames (DataFrame has no `.tolist()`)
    and the contract check then complained `expected list, got str`. Lock in
    that DataFrames/Series are converted via `to_numpy().tolist()` instead."""
    import pandas as pd  # noqa: F401  — used in the generated module string

    pandas_load_data = """\
import pandas as pd


def load_data():
    X_train = pd.DataFrame([[1.0, 2.0], [3.0, 4.0]], columns=["a", "b"])
    X_test = pd.DataFrame([[5.0, 6.0]], columns=["a", "b"])
    y_train = pd.Series([1.0, 2.0], name="y")
    y_test = pd.Series([3.0], name="y")
    return X_train, X_test, y_train, y_test
"""
    tool = _module_tool("load_data", pandas_load_data)
    v = ToolVerifier(LocalSandbox())
    result = await v.verify(tool, _LOAD_CONTRACT, workspace=None)
    assert result.verified is True, result.errors


async def test_verifier_handles_arbitrary_contract():
    """Verifier should work with custom dict-shaped contracts, not just regression."""
    custom = ToolContract(
        name="square",
        description="square",
        entrypoint="square",
        module_filename="square.py",
        params_schema={"x": "float"},
        returns_schema={"result": "float"},
    )
    tool = _module_tool(
        "square",
        "def square(x):\n    return {'result': x * x}\n",
        entrypoint="square",
    )
    v = ToolVerifier(LocalSandbox())
    result = await v.verify(tool, custom, workspace=None, fixtures={"x": 3.0})
    assert result.verified is True, result.errors
    assert result.sample_output["result"] == 9.0
