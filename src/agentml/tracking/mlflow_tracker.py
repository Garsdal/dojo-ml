"""MLflow-based tracking connector — logs to MLflow Tracking."""

from __future__ import annotations

from typing import Any

from agentml.interfaces.tracking import TrackingConnector
from agentml.utils.logging import get_logger

logger = get_logger(__name__)


class MlflowTracker(TrackingConnector):
    """Tracks experiments using MLflow >= 3.0.

    Maps AgentML experiment IDs to MLflow runs inside a single MLflow experiment.
    Each AgentML experiment gets its own MLflow run, keyed by experiment_id tag.
    """

    def __init__(
        self,
        tracking_uri: str = "file:./mlruns",
        experiment_name: str = "agentml",
        artifact_location: str | None = None,
    ) -> None:
        import mlflow

        mlflow.set_tracking_uri(tracking_uri)
        self._client = mlflow.MlflowClient(tracking_uri=tracking_uri)
        self._tracking_uri = tracking_uri

        # Get or create the MLflow experiment
        experiment = self._client.get_experiment_by_name(experiment_name)
        if experiment is None:
            self._experiment_id = self._client.create_experiment(
                experiment_name,
                artifact_location=artifact_location,
            )
        else:
            self._experiment_id = experiment.experiment_id

        self._experiment_name = experiment_name

        # Cache: agentml_experiment_id → mlflow_run_id
        self._run_cache: dict[str, str] = {}

        logger.info(
            "mlflow_tracker_initialized",
            tracking_uri=tracking_uri,
            experiment_name=experiment_name,
            experiment_id=self._experiment_id,
        )

    def _get_or_create_run(self, experiment_id: str) -> str:
        """Get existing MLflow run for this experiment_id, or create one."""
        if experiment_id in self._run_cache:
            return self._run_cache[experiment_id]

        # Search for existing run with this tag
        runs = self._client.search_runs(
            experiment_ids=[self._experiment_id],
            filter_string=f'tags."agentml.experiment_id" = "{experiment_id}"',
            max_results=1,
        )
        if runs:
            run_id = runs[0].info.run_id
        else:
            run = self._client.create_run(
                self._experiment_id,
                tags={"agentml.experiment_id": experiment_id},
            )
            run_id = run.info.run_id

        self._run_cache[experiment_id] = run_id
        return run_id

    async def log_metrics(self, experiment_id: str, metrics: dict[str, float]) -> None:
        run_id = self._get_or_create_run(experiment_id)
        for key, value in metrics.items():
            self._client.log_metric(run_id, key, value)
        logger.debug("mlflow_metrics_logged", experiment_id=experiment_id, count=len(metrics))

    async def log_params(self, experiment_id: str, params: dict[str, Any]) -> None:
        run_id = self._get_or_create_run(experiment_id)
        flat_params = self._flatten_params(params)
        for key, value in flat_params.items():
            self._client.log_param(run_id, key, str(value))
        logger.debug("mlflow_params_logged", experiment_id=experiment_id, count=len(flat_params))

    async def log_artifact(self, experiment_id: str, artifact_path: str) -> None:
        run_id = self._get_or_create_run(experiment_id)
        self._client.log_artifact(run_id, artifact_path)
        logger.debug("mlflow_artifact_logged", experiment_id=experiment_id, path=artifact_path)

    async def get_metrics(self, experiment_id: str) -> dict[str, float]:
        run_id = self._get_or_create_run(experiment_id)
        run = self._client.get_run(run_id)
        return {k: float(v) for k, v in run.data.metrics.items()}

    async def close(self) -> None:
        """No-op — MLflow client does not require explicit cleanup."""
        pass

    @staticmethod
    def _flatten_params(params: dict[str, Any], prefix: str = "") -> dict[str, str]:
        """Flatten nested dicts into dot-separated keys for MLflow params."""
        flat: dict[str, str] = {}
        for key, value in params.items():
            full_key = f"{prefix}.{key}" if prefix else key
            if isinstance(value, dict):
                flat.update(MlflowTracker._flatten_params(value, full_key))
            else:
                flat[full_key] = str(value)
        return flat
