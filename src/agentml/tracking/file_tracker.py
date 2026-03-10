"""File-based tracking connector — JSON metric logging."""

import json
from pathlib import Path
from typing import Any

from agentml.interfaces.tracking import TrackingConnector
from agentml.utils.serialization import to_json


class FileTracker(TrackingConnector):
    """Tracks experiment metrics and params in JSON files."""

    def __init__(self, base_dir: Path | None = None) -> None:
        self.base_dir = base_dir or Path(".agentml/tracking")
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _experiment_dir(self, experiment_id: str) -> Path:
        d = self.base_dir / experiment_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    async def log_metrics(self, experiment_id: str, metrics: dict[str, float]) -> None:
        """Log metrics to a JSON file."""
        path = self._experiment_dir(experiment_id) / "metrics.json"
        existing = self._load_json(path)
        existing.update(metrics)
        path.write_text(to_json(existing))

    async def log_params(self, experiment_id: str, params: dict[str, Any]) -> None:
        """Log parameters to a JSON file."""
        path = self._experiment_dir(experiment_id) / "params.json"
        existing = self._load_json(path)
        existing.update(params)
        path.write_text(to_json(existing))

    async def log_artifact(self, experiment_id: str, artifact_path: str) -> None:
        """Log an artifact reference."""
        path = self._experiment_dir(experiment_id) / "artifacts.json"
        artifacts = self._load_json_list(path)
        artifacts.append(artifact_path)
        path.write_text(to_json(artifacts))

    async def get_metrics(self, experiment_id: str) -> dict[str, float]:
        """Get logged metrics for an experiment."""
        path = self._experiment_dir(experiment_id) / "metrics.json"
        return self._load_json(path)

    async def close(self) -> None:
        """No-op — file tracker has no resources to clean up."""
        pass

    @staticmethod
    def _load_json(path: Path) -> dict:
        if path.exists():
            return json.loads(path.read_text())
        return {}

    @staticmethod
    def _load_json_list(path: Path) -> list:
        if path.exists():
            return json.loads(path.read_text())
        return []
