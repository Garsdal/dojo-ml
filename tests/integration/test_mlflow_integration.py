"""Integration tests: full MLflow tracking flow through the LabEnvironment."""

import pytest

from agentml.agents.backends.stub import StubAgentBackend
from agentml.agents.orchestrator import AgentOrchestrator
from agentml.api.deps import build_lab
from agentml.config.settings import MemorySettings, Settings, StorageSettings, TrackingSettings


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


async def _run_stub(lab, prompt: str) -> None:
    """Helper: run the stub backend through the orchestrator."""
    backend = StubAgentBackend()
    orchestrator = AgentOrchestrator(lab, backend)
    run = await orchestrator.start(prompt)
    await orchestrator.execute(run)


async def test_stub_agent_logs_to_mlflow(lab) -> None:
    """StubAgentBackend run should log metrics + params to MLflow."""
    await _run_stub(lab, "Test MLflow integration")

    # Verify experiments were created
    experiments = await lab.experiment_store.list()
    assert len(experiments) == 1
    exp = experiments[0]

    assert exp.result is not None
    assert exp.result.metrics["accuracy"] == pytest.approx(0.95)

    tracked_metrics = await lab.tracking.get_metrics(exp.id)
    assert tracked_metrics["accuracy"] == pytest.approx(0.95)
    assert tracked_metrics["f1_score"] == pytest.approx(0.93)


async def test_multiple_experiments_tracked_separately(lab) -> None:
    """Each experiment should have its own MLflow run."""
    await _run_stub(lab, "Task 1")
    await _run_stub(lab, "Task 2")

    experiments = await lab.experiment_store.list()
    assert len(experiments) == 2

    m1 = await lab.tracking.get_metrics(experiments[0].id)
    m2 = await lab.tracking.get_metrics(experiments[1].id)

    assert m1["accuracy"] == pytest.approx(0.95)
    assert m2["accuracy"] == pytest.approx(0.95)

    from agentml.tracking.mlflow_tracker import MlflowTracker

    assert isinstance(lab.tracking, MlflowTracker)
    assert experiments[0].id != experiments[1].id
