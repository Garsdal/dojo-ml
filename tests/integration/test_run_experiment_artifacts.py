"""End-to-end: agent's train code writes a file under DOJO_ARTIFACTS_DIR;
framework ingests it via ArtifactStore + tracking and records on CodeRun."""

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
        X_train = [[1.0], [2.0], [3.0]]
        X_test = [[4.0], [5.0]]
        y_train = [1.0, 2.0, 3.0]
        y_test = [4.0, 5.0]
        return X_train, X_test, y_train, y_test
    """
)

_EVALUATE = textwrap.dedent(
    """
    def evaluate(y_pred, *, X_train, X_test, y_train, y_test, artifacts_dir=None):
        diffs = [abs(a - b) for a, b in zip(y_test, y_pred)]
        mae = sum(diffs) / len(diffs)
        return {"rmse": mae, "r2": 0.0, "mae": mae}
    """
)

_TRAIN = textwrap.dedent(
    """
    import os
    from pathlib import Path

    def train(X_train, y_train, X_test, **_):
        artifacts = Path(os.environ["DOJO_ARTIFACTS_DIR"])
        (artifacts / "evaluation_summary.html").write_text("<html>ok</html>")
        return [4.0, 5.0]
    """
)


async def test_run_experiment_ingests_artifacts(lab, settings, tmp_path):
    workspace = Workspace(
        source=WorkspaceSource.LOCAL,
        path=str(tmp_path / "ws"),
        ready=True,
        python_path=None,
    )
    Path(workspace.path).mkdir(parents=True, exist_ok=True)
    domain = Domain(name="t", prompt="t", workspace=workspace)
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
            "hypothesis": "writes an artifact",
            "train_code": _TRAIN,
        }
    )

    assert result.error is None, result.error
    assert result.data["status"] == "completed", result.data

    experiment_id = result.data["experiment_id"]
    artifacts_dir = (
        Path(settings.storage.base_dir)
        / "domains"
        / domain.id
        / "runs"
        / experiment_id
        / "artifacts"
    )
    assert (artifacts_dir / "evaluation_summary.html").read_text() == "<html>ok</html>"

    saved = await lab.artifact_store.list(prefix=f"experiments/{experiment_id}/artifacts/")
    assert any(p.endswith("evaluation_summary.html") for p in saved), saved

    exp = await lab.experiment_store.load(experiment_id)
    assert exp is not None
    assert len(exp.result.code_runs) == 1
    assert any(
        p.endswith("evaluation_summary.html") for p in exp.result.code_runs[0].artifact_paths
    ), exp.result.code_runs[0].artifact_paths
