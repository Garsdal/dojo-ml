"""Unit tests for the failure branches of _ingest_artifacts.

The helper deliberately swallows storage and tracking failures so that
artifact-ingestion problems do not fail an otherwise-successful run.
These tests verify the swallow-and-log behaviour for each branch.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest
from structlog.testing import capture_logs

from dojo.storage.local.artifact import LocalArtifactStore
from dojo.tools.experiments import _ingest_artifacts
from dojo.tracking.noop_tracker import NoopTracker


class _FailingArtifactStore(LocalArtifactStore):
    """Store that raises on every save call. Used to drive the
    ``artifact_ingest_failed`` branch of ``_ingest_artifacts``."""

    async def save(self, artifact_id: str, data: bytes, *, content_type: str = "") -> str:
        raise RuntimeError("boom: store unavailable")


class _FailingTracker(NoopTracker):
    """Tracker that raises on every log_artifact call. Used to drive the
    ``artifact_track_failed`` branch of ``_ingest_artifacts``."""

    async def log_artifact(self, experiment_id: str, artifact_path: str) -> None:
        raise RuntimeError("boom: tracking unavailable")


@pytest.fixture
def artifacts_dir(tmp_path: Path) -> Path:
    d = tmp_path / "artifacts"
    d.mkdir()
    (d / "summary.html").write_text("<html>ok</html>")
    return d


async def test_ingest_artifacts_swallows_store_failure(
    tmp_path: Path,
    artifacts_dir: Path,
    lab,
):
    patched_lab = dataclasses.replace(
        lab,
        artifact_store=_FailingArtifactStore(base_dir=tmp_path / "store"),
        tracking=NoopTracker(),
    )

    with capture_logs() as logs:
        paths = await _ingest_artifacts(
            lab=patched_lab,
            experiment_id="exp-1",
            artifacts_dir=artifacts_dir,
        )

    assert paths == [], "store failure should not produce any successful paths"
    assert any(log.get("event") == "artifact_ingest_failed" for log in logs), (
        f"expected artifact_ingest_failed log entry, got: {[entry.get('event') for entry in logs]}"
    )


async def test_ingest_artifacts_swallows_tracking_failure(
    tmp_path: Path,
    artifacts_dir: Path,
    lab,
):
    patched_lab = dataclasses.replace(
        lab,
        artifact_store=LocalArtifactStore(base_dir=tmp_path / "store"),
        tracking=_FailingTracker(),
    )

    with capture_logs() as logs:
        paths = await _ingest_artifacts(
            lab=patched_lab,
            experiment_id="exp-1",
            artifacts_dir=artifacts_dir,
        )

    # Tracking failure must NOT remove the path from the returned list —
    # the file is in the artifact store; only the side-effect logging failed.
    assert paths == ["experiments/exp-1/artifacts/summary.html"]
    assert any(log.get("event") == "artifact_track_failed" for log in logs), (
        f"expected artifact_track_failed log entry, got: {[entry.get('event') for entry in logs]}"
    )
