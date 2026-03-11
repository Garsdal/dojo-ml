"""Dependency builder — constructs LabEnvironment from settings."""

from pathlib import Path

from agentml.compute.local import LocalCompute
from agentml.config.settings import Settings
from agentml.interfaces.memory_store import MemoryStore
from agentml.interfaces.tracking import TrackingConnector
from agentml.runtime.lab import LabEnvironment
from agentml.sandbox.local import LocalSandbox
from agentml.storage.local_artifact import LocalArtifactStore
from agentml.storage.local_domain import LocalDomainStore
from agentml.storage.local_experiment import LocalExperimentStore
from agentml.storage.local_knowledge_link import LocalKnowledgeLinkStore
from agentml.utils.logging import get_logger

logger = get_logger(__name__)


def _build_tracking(settings: Settings) -> TrackingConnector:
    """Build tracking connector from settings."""
    if not settings.tracking.enabled:
        from agentml.tracking.noop_tracker import NoopTracker

        logger.info("tracking_disabled")
        return NoopTracker()

    backend = settings.tracking.backend

    if backend == "mlflow":
        try:
            from agentml.tracking.mlflow_tracker import MlflowTracker
        except ImportError as e:
            raise ImportError(
                "MLflow is required for tracking.backend='mlflow'. "
                "Install it with: pip install agentml[mlflow]"
            ) from e
        logger.info("tracking_backend", backend="mlflow", uri=settings.tracking.mlflow_tracking_uri)
        return MlflowTracker(
            tracking_uri=settings.tracking.mlflow_tracking_uri,
            experiment_name=settings.tracking.mlflow_experiment_name,
            artifact_location=settings.tracking.mlflow_artifact_location,
        )

    if backend == "file":
        from agentml.tracking.file_tracker import FileTracker

        base = Path(settings.storage.base_dir) / "tracking"
        logger.info("tracking_backend", backend="file", path=str(base))
        return FileTracker(base_dir=base)

    raise ValueError(f"Unknown tracking backend: {backend!r}")


def _build_memory(settings: Settings) -> MemoryStore:
    """Build memory store from settings."""
    backend = settings.memory.backend

    if backend == "local":
        from agentml.storage.local_memory import LocalMemoryStore

        base = Path(settings.storage.base_dir) / "memory"
        logger.info("memory_backend", backend="local", path=str(base))
        return LocalMemoryStore(base_dir=base)

    raise ValueError(f"Unknown memory backend: {backend!r}")


def build_lab(settings: Settings) -> LabEnvironment:
    """Construct the full LabEnvironment from application settings.

    Args:
        settings: Application settings.

    Returns:
        A fully wired LabEnvironment.
    """
    base = Path(settings.storage.base_dir)

    return LabEnvironment(
        compute=LocalCompute(),
        sandbox=LocalSandbox(timeout=settings.sandbox.timeout),
        experiment_store=LocalExperimentStore(base_dir=base / "experiments"),
        artifact_store=LocalArtifactStore(base_dir=base / "artifacts"),
        memory_store=_build_memory(settings),
        tracking=_build_tracking(settings),
        domain_store=LocalDomainStore(base_dir=base / "domains"),
        knowledge_link_store=LocalKnowledgeLinkStore(base_dir=base / "knowledge_links"),
    )
