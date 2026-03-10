"""Tracking connector interface for metrics and parameter logging."""

from abc import ABC, abstractmethod
from typing import Any


class TrackingConnector(ABC):
    """Abstract base class for experiment tracking."""

    @abstractmethod
    async def log_metrics(self, experiment_id: str, metrics: dict[str, float]) -> None:
        """Log metrics for an experiment.

        Args:
            experiment_id: The experiment ID.
            metrics: Key-value metric pairs.
        """
        ...

    @abstractmethod
    async def log_params(self, experiment_id: str, params: dict[str, Any]) -> None:
        """Log parameters for an experiment.

        Args:
            experiment_id: The experiment ID.
            params: Key-value parameter pairs.
        """
        ...

    @abstractmethod
    async def log_artifact(self, experiment_id: str, artifact_path: str) -> None:
        """Log an artifact for an experiment.

        Args:
            experiment_id: The experiment ID.
            artifact_path: Path to the artifact.
        """
        ...

    @abstractmethod
    async def get_metrics(self, experiment_id: str) -> dict[str, float]:
        """Get all logged metrics for an experiment.

        Args:
            experiment_id: The experiment ID.

        Returns:
            Dictionary of metric key-value pairs.
        """
        ...

    async def close(self) -> None:
        """Clean up resources. Default no-op."""
        pass
