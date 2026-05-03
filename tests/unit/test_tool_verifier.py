"""Unit tests for ToolVerifier."""

from __future__ import annotations

from dojo.core.domain import DomainTool, ToolType
from dojo.core.task import TASK_TYPE_REGISTRY, Task, TaskType, ToolContract
from dojo.runtime.tool_verifier import ToolVerifier, verify_required_tools
from dojo.sandbox.local import LocalSandbox


def _spec_tool(name: str, code: str, *, params: dict | None = None) -> DomainTool:
    return DomainTool(
        name=name,
        description=f"{name} tool",
        type=ToolType.DATA_LOADER if name == "load_data" else ToolType.EVALUATOR,
        executable=True,
        code=code,
        parameters=params or {},
    )


# Contract fixtures from the registry — we test against the actual contract
# the freeze gate will use.
_REG = TASK_TYPE_REGISTRY[TaskType.REGRESSION]
_LOAD_CONTRACT = next(c for c in _REG.required_tools if c.name == "load_data")
_EVAL_CONTRACT = next(c for c in _REG.required_tools if c.name == "evaluate")


GOOD_LOAD_DATA = """\
import json
print(json.dumps({
    "X_train": [[1.0, 2.0], [3.0, 4.0]],
    "X_test":  [[5.0, 6.0]],
    "y_train": [1.0, 2.0],
    "y_test":  [3.0],
}))
"""

# Missing y_test
BAD_LOAD_DATA = """\
import json
print(json.dumps({"X_train": [[1.0]], "X_test": [[2.0]], "y_train": [1.0]}))
"""

GOOD_EVALUATE = """\
import json
# y_pred is injected as a local variable
y_test = [1.0, 2.0, 3.0]
diffs = [a - b for a, b in zip(y_pred, y_test)]
mse = sum(d*d for d in diffs) / len(diffs)
import math
mae = sum(abs(d) for d in diffs) / len(diffs)
print(json.dumps({"rmse": math.sqrt(mse), "r2": 1.0, "mae": mae}))
"""

# Returns wrong shape — list instead of dict
BAD_EVALUATE_SHAPE = """\
import json
print(json.dumps([1, 2, 3]))
"""

# Crashes
BAD_EVALUATE_RAISES = """\
raise RuntimeError("boom")
"""


async def test_verifier_passes_for_good_load_data():
    tool = _spec_tool("load_data", GOOD_LOAD_DATA)
    v = ToolVerifier(LocalSandbox())
    result = await v.verify(tool, _LOAD_CONTRACT, workspace=None)
    assert result.verified is True, result.errors
    assert result.errors == []
    assert "X_train" in result.sample_output
    assert result.sample_output["X_train"]["length"] == 2


async def test_verifier_flags_missing_keys():
    tool = _spec_tool("load_data", BAD_LOAD_DATA)
    v = ToolVerifier(LocalSandbox())
    result = await v.verify(tool, _LOAD_CONTRACT, workspace=None)
    assert result.verified is False
    assert any("y_test" in e for e in result.errors)


async def test_verifier_passes_for_good_evaluate_with_fixture():
    tool = _spec_tool("evaluate", GOOD_EVALUATE, params={"y_pred": {"type": "array"}})
    v = ToolVerifier(LocalSandbox())
    result = await v.verify(
        tool,
        _EVAL_CONTRACT,
        workspace=None,
        fixtures={"y_pred": [1.0, 2.0, 3.0]},
    )
    assert result.verified is True, result.errors
    assert {"rmse", "r2", "mae"}.issubset(result.sample_output.keys())


async def test_verifier_requires_fixture_when_contract_has_params():
    tool = _spec_tool("evaluate", GOOD_EVALUATE)
    v = ToolVerifier(LocalSandbox())
    result = await v.verify(tool, _EVAL_CONTRACT, workspace=None)
    assert result.verified is False
    assert any("y_pred" in e for e in result.errors)


async def test_verifier_catches_crashes():
    tool = _spec_tool("evaluate", BAD_EVALUATE_RAISES)
    v = ToolVerifier(LocalSandbox())
    result = await v.verify(tool, _EVAL_CONTRACT, workspace=None, fixtures={"y_pred": [1.0]})
    assert result.verified is False
    assert any("exit" in e.lower() for e in result.errors)


async def test_verifier_rejects_non_object_output():
    tool = _spec_tool("evaluate", BAD_EVALUATE_SHAPE)
    v = ToolVerifier(LocalSandbox())
    result = await v.verify(tool, _EVAL_CONTRACT, workspace=None, fixtures={"y_pred": [1.0]})
    assert result.verified is False


async def test_verifier_rejects_empty_code():
    tool = _spec_tool("load_data", "")
    v = ToolVerifier(LocalSandbox())
    result = await v.verify(tool, _LOAD_CONTRACT, workspace=None)
    assert result.verified is False
    assert any("no code" in e.lower() for e in result.errors)


async def test_verify_required_tools_threads_y_test_into_evaluate():
    load = _spec_tool("load_data", GOOD_LOAD_DATA)
    evaluate = _spec_tool("evaluate", GOOD_EVALUATE, params={"y_pred": {"type": "array"}})
    task = Task(type=TaskType.REGRESSION)

    out = await verify_required_tools(
        [load, evaluate], task, sandbox=LocalSandbox(), workspace=None
    )

    assert load.verification is not None
    assert load.verification.verified is True
    assert evaluate.verification is not None
    # If load_data succeeded, y_pred fixture should have been threaded through
    # and evaluate should also pass.
    assert evaluate.verification.verified is True, evaluate.verification.errors
    assert len(out) == 2


async def test_verify_required_tools_skips_missing_tool():
    """Missing required tools shouldn't crash — they just stay unverified."""
    load = _spec_tool("load_data", GOOD_LOAD_DATA)
    task = Task(type=TaskType.REGRESSION)
    out = await verify_required_tools([load], task, sandbox=LocalSandbox(), workspace=None)
    assert out[0].verification is not None
    assert out[0].verification.verified is True


async def test_verify_required_tools_evaluate_fails_when_load_data_fails():
    load = _spec_tool("load_data", BAD_LOAD_DATA)
    evaluate = _spec_tool("evaluate", GOOD_EVALUATE, params={"y_pred": {"type": "array"}})
    task = Task(type=TaskType.REGRESSION)
    await verify_required_tools([load, evaluate], task, sandbox=LocalSandbox(), workspace=None)
    assert load.verification is not None and not load.verification.verified
    # No y_test → no fixture → evaluate's verification is missing-fixture
    assert evaluate.verification is not None
    assert not evaluate.verification.verified
    assert any("y_pred" in e for e in evaluate.verification.errors)


async def test_verifier_handles_arbitrary_contract():
    """Verifier should work with custom contracts, not just regression."""
    custom = ToolContract(
        name="square",
        description="square",
        params_schema={"x": "float"},
        returns_schema={"result": "float"},
    )
    tool = _spec_tool("square", "import json\nprint(json.dumps({'result': x * x}))")
    v = ToolVerifier(LocalSandbox())
    result = await v.verify(tool, custom, workspace=None, fixtures={"x": 3.0})
    assert result.verified is True
    assert result.sample_output["result"] == 9.0
