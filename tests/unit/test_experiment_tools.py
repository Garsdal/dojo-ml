"""Phase 4 — tests for the experiment MCP surface.

The agent's per-experiment surface is exactly one tool: ``run_experiment``.
The dropped tools (``create_experiment``, ``complete_experiment``,
``fail_experiment``, ``run_experiment_code``) are intentionally not tested
here — their lifecycle transitions still happen, just inside ``run_experiment``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dojo.core.domain import Domain, DomainTool, ToolType, VerificationResult, Workspace
from dojo.core.experiment import Experiment, Hypothesis
from dojo.core.state_machine import ExperimentState
from dojo.core.task import TaskType
from dojo.runtime.task_service import TaskService
from dojo.tools.base import ToolDef
from dojo.tools.experiments import create_experiment_tools

_LOAD_DATA = """\
def load_data():
    return [[1.0]], [[2.0]], [1.0], [2.0]
"""

_EVALUATE = """\
import math
from load_data import load_data


def evaluate(y_pred):
    _, _, _, y_test = load_data()
    diffs = [a - b for a, b in zip(y_pred, y_test)]
    mse = sum(d * d for d in diffs) / len(diffs)
    mae = sum(abs(d) for d in diffs) / len(diffs)
    return {"rmse": math.sqrt(mse), "r2": 1.0, "mae": mae}
"""


def _verified_tool(name: str, code: str) -> DomainTool:
    return DomainTool(
        name=name,
        description=f"{name} tool",
        type=ToolType.DATA_LOADER if name == "load_data" else ToolType.EVALUATOR,
        module_filename=f"{name}.py",
        entrypoint=name,
        code=code,
        verification=VerificationResult(verified=True),
    )


@pytest.fixture
async def ready_domain(lab, tmp_path: Path) -> Domain:
    """Create a domain with a workspace and a frozen task containing real
    load_data + evaluate modules. Sufficient for ``run_experiment`` calls."""
    workspace_dir = tmp_path / "ws"
    workspace_dir.mkdir()

    domain = Domain(
        name="ready",
        workspace=Workspace(path=str(workspace_dir), ready=True),
    )
    await lab.domain_store.save(domain)

    svc = TaskService(lab)
    await svc.create(domain.id, task_type=TaskType.REGRESSION)
    domain = await lab.domain_store.load(domain.id)
    domain.task.tools = [
        _verified_tool("load_data", _LOAD_DATA),
        _verified_tool("evaluate", _EVALUATE),
    ]
    await lab.domain_store.save(domain)
    await svc.freeze(domain.id)
    return await lab.domain_store.load(domain.id)


def _tools_by_name(lab) -> dict[str, ToolDef]:
    return {t.name: t for t in create_experiment_tools(lab)}


async def test_phase4_surface_only_exposes_four_tools(lab):
    """The agent sees run_experiment + three read-only tools — nothing else."""
    names = sorted(_tools_by_name(lab))
    assert names == [
        "compare_experiments",
        "get_experiment",
        "list_experiments",
        "run_experiment",
    ]


async def test_run_experiment_completes_with_metrics(lab, ready_domain):
    tools = _tools_by_name(lab)
    train_code = "def train():\n    return [2.0]\n"  # perfect — y_test == [2.0]

    result = await tools["run_experiment"].handler(
        {
            "domain_id": ready_domain.id,
            "hypothesis": "trivial constant predictor",
            "train_code": train_code,
        }
    )

    assert not result.is_error, result.error
    assert result.data["status"] == "completed"
    metrics = result.data["metrics"]
    assert set(metrics) == {"rmse", "r2", "mae"}
    assert metrics["rmse"] == pytest.approx(0.0)

    exp = await lab.experiment_store.load(result.data["experiment_id"])
    assert exp is not None
    assert exp.state == ExperimentState.COMPLETED
    assert exp.result.metrics == metrics


async def test_run_experiment_fails_when_train_raises(lab, ready_domain):
    tools = _tools_by_name(lab)
    train_code = "def train():\n    raise RuntimeError('boom')\n"

    result = await tools["run_experiment"].handler(
        {
            "domain_id": ready_domain.id,
            "hypothesis": "broken",
            "train_code": train_code,
        }
    )
    assert result.data["status"] == "failed"
    assert "boom" in result.data["error"]

    exp = await lab.experiment_store.load(result.data["experiment_id"])
    assert exp.state == ExperimentState.FAILED


async def test_run_experiment_fails_when_no_train_function(lab, ready_domain):
    tools = _tools_by_name(lab)

    result = await tools["run_experiment"].handler(
        {
            "domain_id": ready_domain.id,
            "hypothesis": "no train",
            "train_code": "x = 1\n",
        }
    )
    assert result.data["status"] == "failed"
    # ImportError surfaces clearly in the runner's caught traceback
    assert "train" in result.data["error"].lower()


async def test_run_experiment_rejects_unfrozen_domain(lab, tmp_path):
    """If the domain task isn't frozen, run_experiment refuses with a clear error."""
    domain = Domain(
        name="not-ready",
        workspace=Workspace(path=str(tmp_path), ready=True),
    )
    await lab.domain_store.save(domain)
    svc = TaskService(lab)
    await svc.create(domain.id, task_type=TaskType.REGRESSION)

    tools = _tools_by_name(lab)
    result = await tools["run_experiment"].handler(
        {
            "domain_id": domain.id,
            "hypothesis": "h",
            "train_code": "def train():\n    return [0.0]\n",
        }
    )
    assert result.is_error
    assert "frozen" in result.error.lower()


async def test_run_experiment_rejects_unknown_domain(lab):
    tools = _tools_by_name(lab)
    result = await tools["run_experiment"].handler(
        {
            "domain_id": "does-not-exist",
            "hypothesis": "h",
            "train_code": "def train():\n    return []\n",
        }
    )
    assert result.is_error
    assert "not found" in result.error.lower()


async def test_run_experiment_logs_to_tracking(lab, ready_domain):
    """Phase 4 contract: run_experiment calls tracking.log_metrics on success."""
    tools = _tools_by_name(lab)
    result = await tools["run_experiment"].handler(
        {
            "domain_id": ready_domain.id,
            "hypothesis": "constant",
            "train_code": "def train():\n    return [2.0]\n",
        }
    )
    assert result.data["status"] == "completed"
    metrics = await lab.tracking.get_metrics(result.data["experiment_id"])
    assert set(metrics) == {"rmse", "r2", "mae"}


async def test_get_experiment_returns_full_record(lab):
    """Round-trip via the read-only tool; doesn't need a frozen domain."""
    exp = Experiment(
        domain_id="x",
        hypothesis=Hypothesis(description="t", variables={"a": 1}),
        config={"seed": 42},
    )
    eid = await lab.experiment_store.save(exp)
    tools = _tools_by_name(lab)
    result = await tools["get_experiment"].handler({"experiment_id": eid})
    assert result.data["id"] == eid
    assert result.data["hypothesis"] == "t"
    assert result.data["variables"] == {"a": 1}


async def test_get_experiment_not_found(lab):
    tools = _tools_by_name(lab)
    result = await tools["get_experiment"].handler({"experiment_id": "ghost"})
    assert result.is_error


async def test_list_experiments_returns_all(lab):
    for desc in ("h1", "h2"):
        exp = Experiment(domain_id="x", hypothesis=Hypothesis(description=desc))
        await lab.experiment_store.save(exp)
    tools = _tools_by_name(lab)
    result = await tools["list_experiments"].handler({})
    assert len(result.data) >= 2


async def test_compare_experiments(lab):
    ids: list[str] = []
    for desc in ("h1", "h2"):
        exp = Experiment(domain_id="x", hypothesis=Hypothesis(description=desc))
        ids.append(await lab.experiment_store.save(exp))
    tools = _tools_by_name(lab)
    result = await tools["compare_experiments"].handler({"experiment_ids": ids})
    assert result.data["count"] == 2
