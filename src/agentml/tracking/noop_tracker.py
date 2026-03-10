"""No-op tracking connector — used when tracking is disabled."""

from typing import Any

from agentml.interfaces.tracking import TrackingConnector


class NoopTracker(TrackingConnector):
    """Silently discards all tracking calls."""

    async def log_metrics(self, experiment_id: str, metrics: dict[str, float]) -> None:
        pass

    async def log_params(self, experiment_id: str, params: dict[str, Any]) -> None:
        pass

    async def log_artifact(self, experiment_id: str, artifact_path: str) -> None:
        pass

    async def get_metrics(self, experiment_id: str) -> dict[str, float]:
        return {}

    async def close(self) -> None:
        pass
