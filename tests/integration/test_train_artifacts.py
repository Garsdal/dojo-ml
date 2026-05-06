"""train() can write to artifacts_dir and the bytes land in the archive.

Locks in the v4 contract end-to-end: with `train()` now receiving
``artifacts_dir``, files written from inside ``train()`` (not just
``evaluate()``) must be picked up by the post-run ingestion pipeline.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

from dojo.core.domain import Domain, DomainTool, ToolType, Workspace, WorkspaceSource
from dojo.core.task import TaskType
from dojo.runtime.task_service import TaskService
from dojo.tools.experiments import create_experiment_tools

_LOAD_DATA = textwrap.dedent(
    """
    def load_data():
        X_train = [[1.0], [2.0]]
        X_test = [[3.0]]
        y_train = [10.0, 20.0]
        y_test = [30.0]
        return X_train, X_test, y_train, y_test
    """
)

_EVALUATE = textwrap.dedent(
    """
    def evaluate(y_pred, *, X_train, X_test, y_train, y_test, artifacts_dir):
        (artifacts_dir / "eval_diagnostic.txt").write_text("eval-ok")
        return {"rmse": 0.0, "r2": 1.0, "mae": 0.0}
    """
)

_TRAIN = textwrap.dedent(
    """
    def train(X_train, y_train, X_test, *, artifacts_dir):
        (artifacts_dir / "model.txt").write_text("trained-model")
        return [float(y_train[0])] * len(X_test)
    """
)


async def test_train_artifact_lands_in_archive(lab, tmp_path: Path):
    workspace_dir = tmp_path / "ws"
    workspace_dir.mkdir()
    domain = Domain(
        name="art",
        prompt="art",
        workspace=Workspace(
            source=WorkspaceSource.LOCAL,
            path=str(workspace_dir),
            ready=True,
        ),
    )
    await lab.domain_store.save(domain)

    task_service = TaskService(lab)
    await task_service.create(domain.id, task_type=TaskType.REGRESSION)

    domain = await lab.domain_store.load(domain.id)
    domain.task.tools = [
        DomainTool(
            name="load_data",
            type=ToolType.DATA_LOADER,
            module_filename="load_data.py",
            entrypoint="load_data",
            code=_LOAD_DATA,
        ),
        DomainTool(
            name="evaluate",
            type=ToolType.EVALUATOR,
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
            "hypothesis": "train writes an artifact",
            "train_code": _TRAIN,
        }
    )

    assert result.error is None, result.error
    assert result.data["status"] == "completed", result.data
    experiment_id = result.data["experiment_id"]

    # Both files were ingested into the artifact store
    keys = await lab.artifact_store.list(prefix=f"experiments/{experiment_id}/artifacts/")
    assert any(k.endswith("model.txt") for k in keys), keys
    assert any(k.endswith("eval_diagnostic.txt") for k in keys), keys

    # And recorded on the experiment's CodeRun
    exp = await lab.experiment_store.load(experiment_id)
    assert exp is not None and exp.result is not None
    code_run = exp.result.code_runs[-1]
    assert any("model.txt" in p for p in code_run.artifact_paths), code_run.artifact_paths
    assert any("eval_diagnostic.txt" in p for p in code_run.artifact_paths), code_run.artifact_paths
