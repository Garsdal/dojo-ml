"""Integration tests: full MLflow tracking flow through the LabEnvironment."""

import pytest

from agentml.agents.stub_agent import StubAgent
from agentml.api.deps import build_lab
from agentml.config.settings import MemorySettings, Settings, StorageSettings, TrackingSettings
from agentml.core.task import Task


@pytest.fixture
def lab(tmp_path):
    settings = Settings(
        storage=StorageSettings(base_dir=tmp_path / ".agentml"),
        tracking=TrackingSettings(
            backend="mlflow",
            enabled=True,
            mlflow_tracking_uri=f"file:{tmp_path / 'mlruns'}",
            mlflow_experiment_name="integration-test",
        ),
        memory=MemorySettings(backend="local"),
    )
    return build_lab(settings)


async def test_stub_agent_logs_to_mlflow(lab) -> None:
    """StubAgent run should log metrics + params to MLflow."""
    task = Task(prompt="Test MLflow integration")
    agent = StubAgent()
    result = await agent.run(task, lab)

    assert result.metrics["accuracy"] == pytest.approx(0.95)

    # Verify MLflow received the metrics
    experiments = await lab.experiment_store.list(task_id=task.id)
    assert len(experiments) == 1
    exp = experiments[0]

    tracked_metrics = await lab.tracking.get_metrics(exp.id)
    assert tracked_metrics["accuracy"] == pytest.approx(0.95)
    assert tracked_metrics["f1_score"] == pytest.approx(0.93)


async def test_multiple_experiments_tracked_separately(lab) -> None:
    """Each experiment should have its own MLflow run."""
    agent = StubAgent()

    task1 = Task(prompt="Task 1")
    task2 = Task(prompt="Task 2")

    await agent.run(task1, lab)
    await agent.run(task2, lab)

    exps1 = await lab.experiment_store.list(task_id=task1.id)
    exps2 = await lab.experiment_store.list(task_id=task2.id)

    m1 = await lab.tracking.get_metrics(exps1[0].id)
    m2 = await lab.tracking.get_metrics(exps2[0].id)

    assert m1["accuracy"] == pytest.approx(0.95)
    assert m2["accuracy"] == pytest.approx(0.95)

    from agentml.tracking.mlflow_tracker import MlflowTracker

    assert isinstance(lab.tracking, MlflowTracker)
    assert exps1[0].id != exps2[0].id
    assert lab.tracking._run_cache[exps1[0].id] != lab.tracking._run_cache[exps2[0].id]
