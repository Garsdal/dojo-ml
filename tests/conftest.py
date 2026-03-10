"""Shared test fixtures."""

import tempfile
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from agentml.api.app import create_app
from agentml.api.deps import build_lab
from agentml.config.settings import (
    AgentSettings,
    MemorySettings,
    Settings,
    StorageSettings,
    TrackingSettings,
)
from agentml.runtime.lab import LabEnvironment


@pytest.fixture
def tmp_dir():
    """Provide a temporary directory for test data."""
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


@pytest.fixture
def settings(tmp_dir: Path) -> Settings:
    """Settings pointing at a temp directory (file tracker, stub agent)."""
    return Settings(
        storage=StorageSettings(base_dir=tmp_dir / ".agentml"),
        tracking=TrackingSettings(backend="file", enabled=True),
        memory=MemorySettings(backend="local"),
        agent=AgentSettings(backend="stub"),
    )


@pytest.fixture
def mlflow_settings(tmp_dir: Path) -> Settings:
    """Settings with MLflow tracking pointing at a temp directory."""
    mlruns = tmp_dir / "mlruns"
    return Settings(
        storage=StorageSettings(base_dir=tmp_dir / ".agentml"),
        tracking=TrackingSettings(
            backend="mlflow",
            enabled=True,
            mlflow_tracking_uri=f"file:{mlruns}",
            mlflow_experiment_name="test-agentml",
        ),
        memory=MemorySettings(backend="local"),
    )


@pytest.fixture
def lab(settings: Settings) -> LabEnvironment:
    """Build a LabEnvironment with temp-directory-based backends."""
    return build_lab(settings)


@pytest.fixture
async def client(settings: Settings):
    """Async HTTP client for the FastAPI app."""
    app = create_app(settings)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
async def mlflow_client(mlflow_settings: Settings):
    """Async HTTP client for the FastAPI app (mlflow tracker)."""
    app = create_app(mlflow_settings)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
