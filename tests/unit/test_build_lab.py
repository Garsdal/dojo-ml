"""Unit tests for build_lab() backend dispatch."""

import pytest

from agentml.api.deps import build_lab
from agentml.config.settings import MemorySettings, Settings, StorageSettings, TrackingSettings
from agentml.storage.local_memory import LocalMemoryStore
from agentml.tracking.file_tracker import FileTracker
from agentml.tracking.noop_tracker import NoopTracker


def test_build_lab_file_tracker(tmp_path) -> None:
    settings = Settings(
        storage=StorageSettings(base_dir=tmp_path / ".agentml"),
        tracking=TrackingSettings(backend="file", enabled=True),
        memory=MemorySettings(backend="local"),
    )
    lab = build_lab(settings)
    assert isinstance(lab.tracking, FileTracker)
    assert isinstance(lab.memory_store, LocalMemoryStore)


def test_build_lab_tracking_disabled(tmp_path) -> None:
    settings = Settings(
        storage=StorageSettings(base_dir=tmp_path / ".agentml"),
        tracking=TrackingSettings(enabled=False),
        memory=MemorySettings(backend="local"),
    )
    lab = build_lab(settings)
    assert isinstance(lab.tracking, NoopTracker)


def test_build_lab_mlflow_tracker(tmp_path) -> None:
    settings = Settings(
        storage=StorageSettings(base_dir=tmp_path / ".agentml"),
        tracking=TrackingSettings(
            backend="mlflow",
            enabled=True,
            mlflow_tracking_uri=f"file:{tmp_path / 'mlruns'}",
            mlflow_experiment_name="test",
        ),
        memory=MemorySettings(backend="local"),
    )
    lab = build_lab(settings)
    from agentml.tracking.mlflow_tracker import MlflowTracker

    assert isinstance(lab.tracking, MlflowTracker)


def test_build_lab_unknown_tracking_backend(tmp_path) -> None:
    settings = Settings(
        storage=StorageSettings(base_dir=tmp_path / ".agentml"),
        tracking=TrackingSettings(backend="unknown", enabled=True),
        memory=MemorySettings(backend="local"),
    )
    with pytest.raises(ValueError, match="Unknown tracking backend"):
        build_lab(settings)


def test_build_lab_unknown_memory_backend(tmp_path) -> None:
    settings = Settings(
        storage=StorageSettings(base_dir=tmp_path / ".agentml"),
        tracking=TrackingSettings(backend="file", enabled=True),
        memory=MemorySettings(backend="unknown"),
    )
    with pytest.raises(ValueError, match="Unknown memory backend"):
        build_lab(settings)
