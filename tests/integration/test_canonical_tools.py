"""Phase 4 anti-cheating: the runner imports `evaluate` from the canonical
dir, not the workspace.

If the agent overwrites the workspace's ``evaluate.py`` with a tampered
version that always returns "perfect" metrics, the recorded metric must still
come from the canonical, frozen copy in ``.dojo/domains/{id}/tools/``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dojo.core.domain import Domain, DomainTool, ToolType, VerificationResult, Workspace
from dojo.core.task import TaskType
from dojo.runtime.task_service import TaskService
from dojo.tools.experiments import create_experiment_tools

_HONEST_LOAD_DATA = """\
def load_data():
    return [[1.0]], [[2.0]], [1.0], [2.0]
"""

_HONEST_EVALUATE = """\
import math


def evaluate(y_pred, *, X_train, X_test, y_train, y_test, artifacts_dir=None):
    diffs = [a - b for a, b in zip(y_pred, y_test, strict=True)]
    mse = sum(d * d for d in diffs) / len(diffs)
    mae = sum(abs(d) for d in diffs) / len(diffs)
    return {"rmse": math.sqrt(mse), "r2": 1.0, "mae": mae}
"""

_CHEATING_EVALUATE = """\
def evaluate(y_pred):
    return {"rmse": 0.0, "r2": 1.0, "mae": 0.0}
"""


@pytest.fixture
async def frozen_domain(lab, tmp_path: Path) -> Domain:
    workspace_dir = tmp_path / "ws"
    workspace_dir.mkdir()
    domain = Domain(
        name="cheat-test",
        workspace=Workspace(path=str(workspace_dir), ready=True),
    )
    await lab.domain_store.save(domain)

    svc = TaskService(lab)
    await svc.create(domain.id, task_type=TaskType.REGRESSION)
    domain = await lab.domain_store.load(domain.id)
    domain.task.tools = [
        DomainTool(
            name="load_data",
            type=ToolType.DATA_LOADER,
            module_filename="load_data.py",
            entrypoint="load_data",
            code=_HONEST_LOAD_DATA,
            verification=VerificationResult(verified=True),
        ),
        DomainTool(
            name="evaluate",
            type=ToolType.EVALUATOR,
            module_filename="evaluate.py",
            entrypoint="evaluate",
            code=_HONEST_EVALUATE,
            verification=VerificationResult(verified=True),
        ),
    ]
    await lab.domain_store.save(domain)
    await svc.freeze(domain.id)
    return await lab.domain_store.load(domain.id)


async def test_canonical_files_written_at_freeze(lab, frozen_domain: Domain):
    """After freeze, both modules live in `.dojo/domains/{id}/tools/`."""
    canonical_dir = TaskService(lab).canonical_tools_dir(frozen_domain.id)
    assert (canonical_dir / "load_data.py").exists()
    assert (canonical_dir / "evaluate.py").exists()
    assert "tool_hashes" in frozen_domain.task.config
    hashes = frozen_domain.task.config["tool_hashes"]
    assert {"load_data.py", "evaluate.py"} <= set(hashes)


async def test_workspace_evaluate_tamper_does_not_affect_metric(lab, frozen_domain: Domain):
    """Anti-cheating: even if the workspace `evaluate.py` returns perfect
    metrics, the recorded metric comes from the canonical version because the
    runner inserts the canonical dir first on sys.path."""
    workspace = Path(frozen_domain.workspace.path)
    (workspace / "evaluate.py").write_text(_CHEATING_EVALUATE)

    tools = {t.name: t for t in create_experiment_tools(lab)}
    # train returns predictions that are clearly wrong — honest evaluate would
    # produce non-zero rmse; cheating evaluate would record 0.0.
    train_code = "def train(X_train, y_train, X_test):\n    return [42.0]\n"
    result = await tools["run_experiment"].handler(
        {
            "domain_id": frozen_domain.id,
            "hypothesis": "tamper test",
            "train_code": train_code,
        }
    )

    assert result.data["status"] == "completed", result.data
    metrics = result.data["metrics"]
    # Honest evaluate over y_test=[2.0] vs y_pred=[42.0] → rmse=40.0.
    # Cheating evaluate would return 0.0; we want non-zero, proving canonical wins.
    assert metrics["rmse"] > 0.0
    assert metrics["mae"] > 0.0


async def test_assert_ready_rejects_canonical_tampering(lab, frozen_domain: Domain):
    """Tampering with the canonical file must trip assert_ready — defence in
    depth even if the runtime sys.path machinery is somehow bypassed."""
    from dojo.runtime.task_service import TaskNotReadyError

    canonical_dir = TaskService(lab).canonical_tools_dir(frozen_domain.id)
    (canonical_dir / "evaluate.py").write_text(_CHEATING_EVALUATE)

    with pytest.raises(TaskNotReadyError, match="tampered"):
        TaskService(lab).assert_ready(frozen_domain.id, frozen_domain.task)
