# MLflow + Memory Store — Detailed Implementation Plan

**Scope:** Wire MLflow (≥ 3.0) as a first-class tracking backend alongside the existing `FileTracker`, properly wire the local `MemoryStore`, make both configurable via `config.yaml` / env vars, and connect everything through `agentml start`. Includes comprehensive testing.

---

## Current State Assessment

| Component | Status | Gap |
|---|---|---|
| `TrackingConnector` ABC | ✅ Complete | — |
| `FileTracker` (local JSON) | ✅ Complete | — |
| MLflow tracker | ❌ Missing | No `MlflowTracker` class |
| `MemoryStore` ABC | ✅ Complete | — |
| `LocalMemoryStore` | ✅ Complete | — |
| `TrackingSettings` | ⚠️ Bare | Only `enabled: bool` — no backend selector, no MLflow URI |
| Memory config | ❌ Missing | No `MemorySettings` in settings |
| `build_lab()` | ⚠️ Hardcoded | Always creates `FileTracker` + `LocalMemoryStore` — no config dispatch |
| `agentml start` | ⚠️ Partial | Starts FastAPI only — no MLflow server, no banner info for tracking/memory |
| Tests | ❌ Missing | Zero test files |

---

## Architecture

```
Settings (config.yaml + env vars)
    │
    ▼
build_lab(settings)              ← dispatches on settings.tracking.backend / settings.memory.backend
    │
    ├── tracking.backend == "file"   → FileTracker
    ├── tracking.backend == "mlflow" → MlflowTracker
    │
    ├── memory.backend == "local"    → LocalMemoryStore
    │   (future: "vector" → VectorMemoryStore)
    │
    ▼
LabEnvironment(tracking=..., memory_store=..., ...)
    │
    ▼
FastAPI app.state.lab
    │
    ▼
StubAgent / ExperimentService uses lab.tracking + lab.memory_store
```

---

## Phase A — Configuration Expansion

### A1. Expand `TrackingSettings`

**File:** `src/agentml/config/settings.py`

```python
class TrackingSettings(BaseSettings):
    """Experiment tracking configuration."""
    backend: str = "file"                        # "file" | "mlflow"
    enabled: bool = True

    # MLflow-specific
    mlflow_tracking_uri: str = "file:./mlruns"   # MLflow tracking server URI
    mlflow_experiment_name: str = "agentml"      # Default experiment name
    mlflow_artifact_location: str | None = None  # Override artifact root (optional)
```

**Env vars:** `AGENTML_TRACKING__BACKEND=mlflow`, `AGENTML_TRACKING__MLFLOW_TRACKING_URI=http://localhost:5000`

### A2. Add `MemorySettings`

**File:** `src/agentml/config/settings.py`

```python
class MemorySettings(BaseSettings):
    """Knowledge memory configuration."""
    backend: str = "local"              # "local" (future: "vector", "postgres")
    search_limit: int = 10              # Default number of results from search
```

Add to root `Settings`:

```python
class Settings(BaseSettings):
    ...
    memory: MemorySettings = Field(default_factory=MemorySettings)
```

### A3. Update `defaults.py`

Add default entries for new settings:

```python
DEFAULTS = {
    ...
    "tracking": {
        "backend": "file",
        "enabled": True,
        "mlflow_tracking_uri": "file:./mlruns",
        "mlflow_experiment_name": "agentml",
    },
    "memory": {
        "backend": "local",
        "search_limit": 10,
    },
}
```

### A4. Update `config init` template

**File:** `src/agentml/cli/config.py`

Add tracking and memory sections to the default YAML template:

```yaml
tracking:
  backend: "file"             # "file" or "mlflow"
  enabled: true
  mlflow_tracking_uri: "file:./mlruns"
  mlflow_experiment_name: "agentml"

memory:
  backend: "local"
  search_limit: 10
```

---

## Phase B — MLflow Tracker Implementation

### B1. Add `mlflow` dependency

**File:** `pyproject.toml`

```toml
[project.optional-dependencies]
mlflow = ["mlflow>=3.0"]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.24",
    "pytest-cov>=6.0",
    "ruff>=0.11",
    "mypy>=1.10",
    "mlflow>=3.0",          # dev includes mlflow for testing
]
```

MLflow is an **optional dependency** — imported lazily. The system falls back to `FileTracker` if mlflow is not installed and `backend: mlflow` is requested (with a clear error).

### B2. Create `MlflowTracker`

**File:** `src/agentml/tracking/mlflow_tracker.py`

```python
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
        import mlflow

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
        # MLflow params must be strings; flatten nested dicts
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
```

**Key design decisions:**

1. **One MLflow experiment, many runs:** All AgentML experiments map to runs within a single MLflow experiment (named by `mlflow_experiment_name`). Each run is tagged with `agentml.experiment_id`.
2. **Run caching:** Avoids repeated `search_runs` calls by caching the mapping in-memory.
3. **Lazy import:** `import mlflow` happens inside `__init__` — if mlflow is not installed, the error surfaces at construction time, not at import time.
4. **Param flattening:** MLflow params must be strings and don't support nesting; nested dicts are flattened with dot-notation.

### B3. Expand `TrackingConnector` Interface (Optional Enhancement)

Add a `close()` method for clean shutdown:

**File:** `src/agentml/interfaces/tracking.py`

```python
class TrackingConnector(ABC):
    ...

    async def close(self) -> None:
        """Clean up resources. Default no-op."""
        pass
```

The `MlflowTracker` can use this to end any active runs on shutdown. The `FileTracker` is a no-op.

---

## Phase C — Wiring: Config-Driven Backend Selection

### C1. Update `build_lab()`

**File:** `src/agentml/api/deps.py`

```python
"""Dependency builder — constructs LabEnvironment from settings."""

from pathlib import Path

from agentml.config.settings import Settings
from agentml.runtime.lab import LabEnvironment
from agentml.compute.local import LocalCompute
from agentml.sandbox.local import LocalSandbox
from agentml.storage.local_artifact import LocalArtifactStore
from agentml.storage.local_experiment import LocalExperimentStore
from agentml.interfaces.tracking import TrackingConnector
from agentml.interfaces.memory_store import MemoryStore
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

    raise ValueError(f"Unknown tracking backend: {backend}")


def _build_memory(settings: Settings) -> MemoryStore:
    """Build memory store from settings."""
    backend = settings.memory.backend

    if backend == "local":
        from agentml.storage.local_memory import LocalMemoryStore
        base = Path(settings.storage.base_dir) / "memory"
        logger.info("memory_backend", backend="local", path=str(base))
        return LocalMemoryStore(base_dir=base)

    raise ValueError(f"Unknown memory backend: {backend}")


def build_lab(settings: Settings) -> LabEnvironment:
    """Construct the full LabEnvironment from application settings."""
    base = Path(settings.storage.base_dir)
    return LabEnvironment(
        compute=LocalCompute(),
        sandbox=LocalSandbox(timeout=settings.sandbox.timeout),
        experiment_store=LocalExperimentStore(base_dir=base / "experiments"),
        artifact_store=LocalArtifactStore(base_dir=base / "artifacts"),
        memory_store=_build_memory(settings),
        tracking=_build_tracking(settings),
    )
```

### C2. Create `NoopTracker`

For when `tracking.enabled = false` — a do-nothing implementation.

**File:** `src/agentml/tracking/noop_tracker.py`

```python
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
```

---

## Phase D — CLI & Startup Wiring

### D1. Enhance `agentml start` Banner

**File:** `src/agentml/cli/start.py`

The start command should display which backends are active:

```
$ agentml start

  AgentML v0.1.0
  ✓ FastAPI server  → http://127.0.0.1:8000
  ✓ API docs        → http://127.0.0.1:8000/docs
  ✓ Tracking        → mlflow (uri: file:./mlruns)
  ✓ Memory store    → local (.agentml/memory)

  Press Ctrl+C to stop.
```

Implementation: Read `settings.tracking.backend` and `settings.memory.backend` and print them.

```python
def start(host: str, port: int) -> None:
    import uvicorn
    from agentml.api.app import create_app
    from agentml.config.settings import Settings
    from agentml.utils.logging import setup_logging

    setup_logging()
    settings = Settings.load()
    settings.api.host = host
    settings.api.port = port

    console.print()
    console.print(f"  [bold cyan]AgentML[/bold cyan] v{__version__}")
    console.print(f"  ✓ FastAPI server  → http://{host}:{port}")
    console.print(f"  ✓ API docs        → http://{host}:{port}/docs")

    # Tracking info
    if settings.tracking.enabled:
        if settings.tracking.backend == "mlflow":
            console.print(
                f"  ✓ Tracking        → mlflow ({settings.tracking.mlflow_tracking_uri})"
            )
        else:
            console.print(f"  ✓ Tracking        → {settings.tracking.backend}")
    else:
        console.print("  ✗ Tracking        → disabled")

    # Memory info
    console.print(f"  ✓ Memory store    → {settings.memory.backend}")

    console.print()
    console.print("  Press Ctrl+C to stop.")
    console.print()

    app = create_app(settings)
    uvicorn.run(app, host=host, port=port, log_level="info")
```

### D2. Graceful Shutdown Hook

Register a shutdown event on the FastAPI app to call `tracking.close()`:

**File:** `src/agentml/api/app.py`

```python
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup — lab is already built and attached
    yield
    # Shutdown
    if hasattr(app.state, "lab") and hasattr(app.state.lab.tracking, "close"):
        await app.state.lab.tracking.close()


def create_app(settings: Settings | None = None) -> FastAPI:
    if settings is None:
        settings = Settings.load()

    app = FastAPI(
        title="AgentML",
        description="AI-powered experiment orchestration",
        version=__version__,
        lifespan=lifespan,
    )
    ...
```

---

## Phase E — StubAgent + Memory Store Integration

Currently the `StubAgent` logs metrics and params via `lab.tracking` but does **not** write knowledge atoms to `lab.memory_store`. Fix this:

### E1. StubAgent writes knowledge atoms

**File:** `src/agentml/agents/stub_agent.py`

After completing the experiment, the stub agent should also create a `KnowledgeAtom` and store it:

```python
from agentml.core.knowledge import KnowledgeAtom

# ... inside run(), after experiment completes:

atom = KnowledgeAtom(
    context=f"Task: {task.prompt}",
    claim="Stub model achieves 95% accuracy on test data.",
    action="Use stub model as baseline for comparison.",
    confidence=0.85,
    evidence_ids=[experiment.id],
)
await lab.memory_store.add(atom)
```

This means the full pipeline is exercised:
- Experiment → ExperimentStore ✅
- Metrics → TrackingConnector ✅ (file or mlflow)
- Knowledge → MemoryStore ✅

### E2. ExperimentService also writes knowledge (optional)

The `ExperimentService.complete()` method could optionally accept knowledge atoms and persist them. This formalizes the "learn" step in the lifecycle. For the PoC, having the agent do it directly is sufficient.

---

## Phase F — API Routes for Memory

The knowledge routes already exist and work (`GET /knowledge`, `GET /knowledge/relevant`). Two additions:

### F1. POST /knowledge — create a knowledge atom

**File:** `src/agentml/api/routers/knowledge.py`

```python
class CreateKnowledgeRequest(BaseModel):
    context: str
    claim: str
    action: str = ""
    confidence: float = 0.5
    evidence_ids: list[str] = []


@router.post("", response_model=KnowledgeResponse, status_code=201)
async def create_knowledge(body: CreateKnowledgeRequest, request: Request) -> KnowledgeResponse:
    lab = _get_lab(request)
    atom = KnowledgeAtom(
        context=body.context,
        claim=body.claim,
        action=body.action,
        confidence=body.confidence,
        evidence_ids=body.evidence_ids,
    )
    await lab.memory_store.add(atom)
    return KnowledgeResponse(
        id=atom.id, context=atom.context, claim=atom.claim,
        action=atom.action, confidence=atom.confidence,
        evidence_ids=atom.evidence_ids,
    )
```

### F2. DELETE /knowledge/{id}

```python
@router.delete("/{atom_id}", status_code=204)
async def delete_knowledge(atom_id: str, request: Request) -> None:
    lab = _get_lab(request)
    deleted = await lab.memory_store.delete(atom_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Knowledge atom not found")
```

### F3. GET /tracking/{experiment_id}/metrics

New router for querying tracked metrics:

**File:** `src/agentml/api/routers/tracking.py`

```python
"""Tracking router — query tracked metrics."""

from fastapi import APIRouter, Request
from agentml.runtime.lab import LabEnvironment

router = APIRouter(prefix="/tracking", tags=["tracking"])


def _get_lab(request: Request) -> LabEnvironment:
    return request.app.state.lab


@router.get("/{experiment_id}/metrics")
async def get_tracked_metrics(experiment_id: str, request: Request) -> dict[str, float]:
    lab = _get_lab(request)
    return await lab.tracking.get_metrics(experiment_id)
```

Register in `app.py`:

```python
from agentml.api.routers import experiments, health, knowledge, tasks, tracking

app.include_router(tracking.router)
```

---

## Phase G — Testing

### Directory Structure

```
tests/
├── conftest.py                           # Shared fixtures
├── unit/
│   ├── test_state_machine.py             # State transition validation
│   ├── test_local_memory.py              # LocalMemoryStore round-trip + search
│   ├── test_local_experiment_store.py    # JSON experiment persistence
│   ├── test_local_artifact_store.py      # Binary artifact round-trip
│   ├── test_file_tracker.py             # FileTracker metrics/params round-trip
│   ├── test_mlflow_tracker.py           # MlflowTracker with file:// backend
│   ├── test_noop_tracker.py             # NoopTracker (trivial but covers the type)
│   ├── test_experiment_service.py        # ExperimentService lifecycle
│   ├── test_serialization.py            # JSON encoder for dataclasses/datetime
│   ├── test_settings.py                 # Config loading, defaults, env vars
│   └── test_build_lab.py               # build_lab dispatches correctly
├── integration/
│   ├── test_mlflow_integration.py       # MLflow end-to-end: log → read → verify
│   └── test_memory_integration.py       # Memory store: add → search → verify
└── e2e/
    └── test_full_lifecycle.py            # POST /tasks → GET /tasks/{id} → verify
```

### G1. Shared Fixtures (`tests/conftest.py`)

```python
import asyncio
import tempfile
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from agentml.api.app import create_app
from agentml.config.settings import Settings, StorageSettings, TrackingSettings, MemorySettings


@pytest.fixture
def tmp_dir(tmp_path: Path) -> Path:
    """Provide a clean temp directory for each test."""
    return tmp_path


@pytest.fixture
def settings(tmp_dir: Path) -> Settings:
    """Settings pointing at a temp directory."""
    return Settings(
        storage=StorageSettings(base_dir=tmp_dir / ".agentml"),
        tracking=TrackingSettings(backend="file", enabled=True),
        memory=MemorySettings(backend="local"),
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


@pytest_asyncio.fixture
async def client(settings: Settings) -> AsyncClient:
    """Async test client for the FastAPI app (file tracker)."""
    app = create_app(settings)
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as c:
        yield c


@pytest_asyncio.fixture
async def mlflow_client(mlflow_settings: Settings) -> AsyncClient:
    """Async test client for the FastAPI app (mlflow tracker)."""
    app = create_app(mlflow_settings)
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as c:
        yield c
```

### G2. Unit Tests

#### `test_state_machine.py`

```python
import pytest
from agentml.core.state_machine import ExperimentState, InvalidTransitionError, transition


def test_valid_transitions():
    assert transition(ExperimentState.PENDING, ExperimentState.RUNNING) == ExperimentState.RUNNING
    assert transition(ExperimentState.RUNNING, ExperimentState.COMPLETED) == ExperimentState.COMPLETED
    assert transition(ExperimentState.RUNNING, ExperimentState.FAILED) == ExperimentState.FAILED
    assert transition(ExperimentState.COMPLETED, ExperimentState.ARCHIVED) == ExperimentState.ARCHIVED
    assert transition(ExperimentState.FAILED, ExperimentState.ARCHIVED) == ExperimentState.ARCHIVED


def test_invalid_transitions():
    with pytest.raises(InvalidTransitionError):
        transition(ExperimentState.PENDING, ExperimentState.COMPLETED)
    with pytest.raises(InvalidTransitionError):
        transition(ExperimentState.ARCHIVED, ExperimentState.RUNNING)
    with pytest.raises(InvalidTransitionError):
        transition(ExperimentState.COMPLETED, ExperimentState.RUNNING)
```

#### `test_local_memory.py`

```python
import pytest
from agentml.core.knowledge import KnowledgeAtom
from agentml.storage.local_memory import LocalMemoryStore


@pytest.fixture
def memory_store(tmp_path):
    return LocalMemoryStore(base_dir=tmp_path / "memory")


@pytest.mark.asyncio
async def test_add_and_list(memory_store):
    atom = KnowledgeAtom(context="classification", claim="XGBoost is good", confidence=0.8)
    atom_id = await memory_store.add(atom)
    atoms = await memory_store.list()
    assert len(atoms) == 1
    assert atoms[0].id == atom_id


@pytest.mark.asyncio
async def test_search_keyword(memory_store):
    await memory_store.add(KnowledgeAtom(context="classification tabular", claim="Trees work well"))
    await memory_store.add(KnowledgeAtom(context="nlp text", claim="Transformers dominate"))
    results = await memory_store.search("classification")
    assert len(results) == 1
    assert "Trees" in results[0].claim


@pytest.mark.asyncio
async def test_search_no_match(memory_store):
    await memory_store.add(KnowledgeAtom(context="classification", claim="Test"))
    results = await memory_store.search("quantum computing")
    assert len(results) == 0


@pytest.mark.asyncio
async def test_delete(memory_store):
    atom = KnowledgeAtom(context="test", claim="test")
    await memory_store.add(atom)
    deleted = await memory_store.delete(atom.id)
    assert deleted is True
    atoms = await memory_store.list()
    assert len(atoms) == 0


@pytest.mark.asyncio
async def test_persistence_across_instances(tmp_path):
    store1 = LocalMemoryStore(base_dir=tmp_path / "memory")
    atom = KnowledgeAtom(context="persistent", claim="This persists")
    await store1.add(atom)

    store2 = LocalMemoryStore(base_dir=tmp_path / "memory")
    atoms = await store2.list()
    assert len(atoms) == 1
    assert atoms[0].claim == "This persists"
```

#### `test_mlflow_tracker.py`

```python
import pytest
from agentml.tracking.mlflow_tracker import MlflowTracker


@pytest.fixture
def tracker(tmp_path):
    uri = f"file:{tmp_path / 'mlruns'}"
    return MlflowTracker(
        tracking_uri=uri,
        experiment_name="unit-test",
    )


@pytest.mark.asyncio
async def test_log_and_get_metrics(tracker):
    await tracker.log_metrics("exp-001", {"accuracy": 0.95, "f1": 0.93})
    metrics = await tracker.get_metrics("exp-001")
    assert metrics["accuracy"] == pytest.approx(0.95)
    assert metrics["f1"] == pytest.approx(0.93)


@pytest.mark.asyncio
async def test_log_params(tracker):
    await tracker.log_params("exp-002", {"model": "xgboost", "lr": 0.01})
    # Verify by getting the run directly
    run_id = tracker._get_or_create_run("exp-002")
    run = tracker._client.get_run(run_id)
    assert run.data.params["model"] == "xgboost"
    assert run.data.params["lr"] == "0.01"


@pytest.mark.asyncio
async def test_nested_params_flattened(tracker):
    await tracker.log_params("exp-003", {"hp": {"lr": 0.01, "batch_size": 32}})
    run_id = tracker._get_or_create_run("exp-003")
    run = tracker._client.get_run(run_id)
    assert run.data.params["hp.lr"] == "0.01"
    assert run.data.params["hp.batch_size"] == "32"


@pytest.mark.asyncio
async def test_run_reuse(tracker):
    """Same experiment_id should map to the same MLflow run."""
    await tracker.log_metrics("exp-reuse", {"m1": 1.0})
    run_id_1 = tracker._run_cache["exp-reuse"]
    await tracker.log_metrics("exp-reuse", {"m2": 2.0})
    run_id_2 = tracker._run_cache["exp-reuse"]
    assert run_id_1 == run_id_2

    metrics = await tracker.get_metrics("exp-reuse")
    assert metrics["m1"] == 1.0
    assert metrics["m2"] == 2.0


@pytest.mark.asyncio
async def test_multiple_experiments(tracker):
    """Different experiment_ids get different MLflow runs."""
    await tracker.log_metrics("exp-a", {"acc": 0.9})
    await tracker.log_metrics("exp-b", {"acc": 0.8})
    assert tracker._run_cache["exp-a"] != tracker._run_cache["exp-b"]
```

#### `test_noop_tracker.py`

```python
import pytest
from agentml.tracking.noop_tracker import NoopTracker


@pytest.mark.asyncio
async def test_noop_does_not_raise():
    tracker = NoopTracker()
    await tracker.log_metrics("x", {"a": 1.0})
    await tracker.log_params("x", {"b": "c"})
    await tracker.log_artifact("x", "/some/path")
    metrics = await tracker.get_metrics("x")
    assert metrics == {}
    await tracker.close()
```

#### `test_file_tracker.py`

```python
import pytest
from agentml.tracking.file_tracker import FileTracker


@pytest.fixture
def tracker(tmp_path):
    return FileTracker(base_dir=tmp_path / "tracking")


@pytest.mark.asyncio
async def test_log_and_get_metrics(tracker):
    await tracker.log_metrics("exp-001", {"acc": 0.95})
    metrics = await tracker.get_metrics("exp-001")
    assert metrics["acc"] == 0.95


@pytest.mark.asyncio
async def test_metrics_accumulate(tracker):
    await tracker.log_metrics("exp-001", {"acc": 0.95})
    await tracker.log_metrics("exp-001", {"f1": 0.93})
    metrics = await tracker.get_metrics("exp-001")
    assert metrics == {"acc": 0.95, "f1": 0.93}


@pytest.mark.asyncio
async def test_log_params(tracker):
    await tracker.log_params("exp-001", {"model": "xgboost"})
    # Params stored in params.json
    import json
    params_file = tracker._experiment_dir("exp-001") / "params.json"
    params = json.loads(params_file.read_text())
    assert params["model"] == "xgboost"
```

#### `test_build_lab.py`

```python
import pytest
from pathlib import Path
from agentml.api.deps import build_lab
from agentml.config.settings import Settings, StorageSettings, TrackingSettings, MemorySettings
from agentml.tracking.file_tracker import FileTracker
from agentml.tracking.noop_tracker import NoopTracker
from agentml.storage.local_memory import LocalMemoryStore


def test_build_lab_file_tracker(tmp_path):
    settings = Settings(
        storage=StorageSettings(base_dir=tmp_path / ".agentml"),
        tracking=TrackingSettings(backend="file", enabled=True),
        memory=MemorySettings(backend="local"),
    )
    lab = build_lab(settings)
    assert isinstance(lab.tracking, FileTracker)
    assert isinstance(lab.memory_store, LocalMemoryStore)


def test_build_lab_tracking_disabled(tmp_path):
    settings = Settings(
        storage=StorageSettings(base_dir=tmp_path / ".agentml"),
        tracking=TrackingSettings(enabled=False),
        memory=MemorySettings(backend="local"),
    )
    lab = build_lab(settings)
    assert isinstance(lab.tracking, NoopTracker)


def test_build_lab_mlflow_tracker(tmp_path):
    settings = Settings(
        storage=StorageSettings(base_dir=tmp_path / ".agentml"),
        tracking=TrackingSettings(
            backend="mlflow",
            enabled=True,
            mlflow_tracking_uri=f"file:{tmp_path / 'mlruns'}",
        ),
        memory=MemorySettings(backend="local"),
    )
    lab = build_lab(settings)
    from agentml.tracking.mlflow_tracker import MlflowTracker
    assert isinstance(lab.tracking, MlflowTracker)


def test_build_lab_unknown_backend(tmp_path):
    settings = Settings(
        storage=StorageSettings(base_dir=tmp_path / ".agentml"),
        tracking=TrackingSettings(backend="unknown", enabled=True),
        memory=MemorySettings(backend="local"),
    )
    with pytest.raises(ValueError, match="Unknown tracking backend"):
        build_lab(settings)
```

#### `test_settings.py`

```python
import pytest
from pathlib import Path
from agentml.config.settings import Settings, TrackingSettings, MemorySettings


def test_default_settings():
    s = Settings()
    assert s.tracking.backend == "file"
    assert s.tracking.enabled is True
    assert s.memory.backend == "local"
    assert s.memory.search_limit == 10


def test_tracking_mlflow_settings():
    t = TrackingSettings(backend="mlflow", mlflow_tracking_uri="http://localhost:5000")
    assert t.backend == "mlflow"
    assert t.mlflow_tracking_uri == "http://localhost:5000"


def test_settings_from_yaml(tmp_path):
    config = tmp_path / "config.yaml"
    config.write_text("""\
tracking:
  backend: mlflow
  mlflow_tracking_uri: "http://mlflow:5000"
  mlflow_experiment_name: my-project
memory:
  backend: local
  search_limit: 20
""")
    s = Settings.load(config_path=config)
    assert s.tracking.backend == "mlflow"
    assert s.tracking.mlflow_tracking_uri == "http://mlflow:5000"
    assert s.memory.search_limit == 20
```

#### `test_experiment_service.py`

```python
import pytest
from agentml.core.experiment import Experiment, ExperimentResult, Hypothesis
from agentml.core.state_machine import ExperimentState
from agentml.runtime.experiment_service import ExperimentService
from agentml.api.deps import build_lab
from agentml.config.settings import Settings, StorageSettings, TrackingSettings, MemorySettings


@pytest.fixture
def lab(tmp_path):
    settings = Settings(
        storage=StorageSettings(base_dir=tmp_path / ".agentml"),
        tracking=TrackingSettings(backend="file", enabled=True),
        memory=MemorySettings(backend="local"),
    )
    return build_lab(settings)


@pytest.fixture
def service(lab):
    return ExperimentService(lab)


@pytest.mark.asyncio
async def test_create_and_get(service):
    exp = Experiment(task_id="task-1", hypothesis=Hypothesis(description="test"))
    exp_id = await service.create(exp)
    loaded = await service.get(exp_id)
    assert loaded is not None
    assert loaded.task_id == "task-1"


@pytest.mark.asyncio
async def test_run_transitions_to_running(service):
    exp = Experiment(task_id="task-1")
    await service.create(exp)
    running = await service.run(exp.id)
    assert running.state == ExperimentState.RUNNING


@pytest.mark.asyncio
async def test_complete_logs_metrics(service, lab):
    exp = Experiment(task_id="task-1")
    await service.create(exp)
    await service.run(exp.id)
    exp.state = ExperimentState.RUNNING
    exp.result = ExperimentResult(metrics={"acc": 0.95})
    completed = await service.complete(exp)
    assert completed.state == ExperimentState.COMPLETED

    # Verify metrics were logged to tracker
    metrics = await lab.tracking.get_metrics(exp.id)
    assert metrics["acc"] == 0.95
```

### G3. Integration Tests

#### `test_mlflow_integration.py`

```python
"""Integration test: full MLflow tracking flow through the LabEnvironment."""

import pytest
from agentml.api.deps import build_lab
from agentml.agents.stub_agent import StubAgent
from agentml.config.settings import Settings, StorageSettings, TrackingSettings, MemorySettings
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


@pytest.mark.asyncio
async def test_stub_agent_logs_to_mlflow(lab):
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


@pytest.mark.asyncio
async def test_multiple_experiments_tracked_separately(lab):
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

    # Both should have metrics (independent runs)
    assert m1["accuracy"] == pytest.approx(0.95)
    assert m2["accuracy"] == pytest.approx(0.95)
```

#### `test_memory_integration.py`

```python
"""Integration test: memory store wired through LabEnvironment."""

import pytest
from agentml.api.deps import build_lab
from agentml.agents.stub_agent import StubAgent
from agentml.config.settings import Settings, StorageSettings, TrackingSettings, MemorySettings
from agentml.core.task import Task
from agentml.core.knowledge import KnowledgeAtom


@pytest.fixture
def lab(tmp_path):
    settings = Settings(
        storage=StorageSettings(base_dir=tmp_path / ".agentml"),
        tracking=TrackingSettings(backend="file", enabled=True),
        memory=MemorySettings(backend="local"),
    )
    return build_lab(settings)


@pytest.mark.asyncio
async def test_stub_agent_creates_knowledge(lab):
    """StubAgent should create a knowledge atom in the memory store."""
    task = Task(prompt="Test memory integration")
    agent = StubAgent()
    await agent.run(task, lab)

    atoms = await lab.memory_store.list()
    assert len(atoms) >= 1
    assert any("Test memory integration" in a.context for a in atoms)


@pytest.mark.asyncio
async def test_knowledge_searchable_after_creation(lab):
    """Knowledge atoms created by the agent should be searchable."""
    task = Task(prompt="classification on tabular data")
    agent = StubAgent()
    await agent.run(task, lab)

    results = await lab.memory_store.search("classification")
    assert len(results) >= 1


@pytest.mark.asyncio
async def test_knowledge_persists_across_tasks(lab):
    """Knowledge accumulated across tasks should all be available."""
    agent = StubAgent()
    await agent.run(Task(prompt="classification problem"), lab)
    await agent.run(Task(prompt="regression problem"), lab)

    atoms = await lab.memory_store.list()
    assert len(atoms) >= 2
```

### G4. End-to-End Tests

#### `test_full_lifecycle.py`

```python
"""E2E test: full task lifecycle through the API."""

import pytest
from httpx import ASGITransport, AsyncClient
from agentml.api.app import create_app
from agentml.config.settings import Settings, StorageSettings, TrackingSettings, MemorySettings


@pytest.fixture
def app(tmp_path):
    settings = Settings(
        storage=StorageSettings(base_dir=tmp_path / ".agentml"),
        tracking=TrackingSettings(backend="file", enabled=True),
        memory=MemorySettings(backend="local"),
    )
    return create_app(settings)


@pytest_asyncio.fixture
async def client(app):
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as c:
        yield c


@pytest.mark.asyncio
async def test_health(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_submit_task_and_get_results(client):
    """Full lifecycle: POST /tasks → GET /tasks/{id} → verify experiments + result."""
    # 1. Create task
    resp = await client.post("/tasks", json={"prompt": "Compare models on iris"})
    assert resp.status_code == 200
    data = resp.json()
    task_id = data["id"]
    assert data["status"] == "completed"
    assert len(data["experiments"]) >= 1
    assert data["experiments"][0]["metrics"] is not None
    assert data["metrics"]["accuracy"] == pytest.approx(0.95)

    # 2. Get task by ID
    resp = await client.get(f"/tasks/{task_id}")
    assert resp.status_code == 200
    task = resp.json()
    assert task["status"] == "completed"
    assert task["id"] == task_id

    # 3. List experiments
    resp = await client.get("/experiments")
    assert resp.status_code == 200
    experiments = resp.json()
    assert len(experiments) >= 1

    # 4. Get experiment by ID
    exp_id = data["experiments"][0]["id"]
    resp = await client.get(f"/experiments/{exp_id}")
    assert resp.status_code == 200
    exp = resp.json()
    assert exp["state"] == "completed"
    assert exp["metrics"]["accuracy"] == pytest.approx(0.95)

    # 5. Knowledge was created
    resp = await client.get("/knowledge")
    assert resp.status_code == 200
    atoms = resp.json()
    assert len(atoms) >= 1

    # 6. Knowledge search
    resp = await client.get("/knowledge/relevant", params={"query": "iris"})
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_tracked_metrics_endpoint(client):
    """Verify GET /tracking/{id}/metrics returns logged metrics."""
    resp = await client.post("/tasks", json={"prompt": "Test tracking"})
    exp_id = resp.json()["experiments"][0]["id"]

    resp = await client.get(f"/tracking/{exp_id}/metrics")
    assert resp.status_code == 200
    metrics = resp.json()
    assert "accuracy" in metrics


@pytest.mark.asyncio
async def test_create_knowledge_via_api(client):
    """POST /knowledge creates a knowledge atom."""
    resp = await client.post("/knowledge", json={
        "context": "image classification",
        "claim": "CNNs outperform MLPs on image data",
        "confidence": 0.9,
    })
    assert resp.status_code == 201
    atom = resp.json()
    assert atom["claim"] == "CNNs outperform MLPs on image data"

    resp = await client.get("/knowledge")
    assert any(a["id"] == atom["id"] for a in resp.json())


@pytest.mark.asyncio
async def test_full_lifecycle_with_mlflow(tmp_path):
    """Same lifecycle but with MLflow tracker."""
    settings = Settings(
        storage=StorageSettings(base_dir=tmp_path / ".agentml"),
        tracking=TrackingSettings(
            backend="mlflow",
            enabled=True,
            mlflow_tracking_uri=f"file:{tmp_path / 'mlruns'}",
            mlflow_experiment_name="e2e-test",
        ),
        memory=MemorySettings(backend="local"),
    )
    app = create_app(settings)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post("/tasks", json={"prompt": "MLflow e2e"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "completed"

        # Verify metrics via tracking endpoint
        exp_id = data["experiments"][0]["id"]
        resp = await client.get(f"/tracking/{exp_id}/metrics")
        assert resp.status_code == 200
        assert resp.json()["accuracy"] == pytest.approx(0.95)
```

---

## File Change Summary

| Action | File | Description |
|---|---|---|
| **Edit** | `pyproject.toml` | Add `mlflow = ["mlflow>=3.0"]` optional dep, add `mlflow>=3.0` to dev deps |
| **Edit** | `src/agentml/config/settings.py` | Expand `TrackingSettings` (backend, mlflow_* fields), add `MemorySettings`, add to `Settings` |
| **Edit** | `src/agentml/config/defaults.py` | Add tracking + memory default entries |
| **Create** | `src/agentml/tracking/mlflow_tracker.py` | `MlflowTracker` implementing `TrackingConnector` |
| **Create** | `src/agentml/tracking/noop_tracker.py` | `NoopTracker` for disabled tracking |
| **Edit** | `src/agentml/interfaces/tracking.py` | Add `close()` method with default no-op |
| **Edit** | `src/agentml/tracking/file_tracker.py` | Add `close()` no-op for interface compliance |
| **Edit** | `src/agentml/api/deps.py` | Rewrite `build_lab()` with `_build_tracking()` + `_build_memory()` dispatch |
| **Edit** | `src/agentml/api/app.py` | Add `lifespan` context manager for graceful shutdown |
| **Edit** | `src/agentml/agents/stub_agent.py` | Add `KnowledgeAtom` creation to exercise memory store |
| **Edit** | `src/agentml/cli/start.py` | Enhanced banner showing active tracking + memory backends |
| **Edit** | `src/agentml/cli/config.py` | Add tracking + memory to default YAML template |
| **Edit** | `src/agentml/api/routers/knowledge.py` | Add `POST /knowledge` and `DELETE /knowledge/{id}` |
| **Create** | `src/agentml/api/routers/tracking.py` | `GET /tracking/{id}/metrics` endpoint |
| **Edit** | `src/agentml/api/app.py` | Register tracking router |
| **Create** | `tests/conftest.py` | Shared fixtures |
| **Create** | `tests/unit/test_state_machine.py` | State transition tests |
| **Create** | `tests/unit/test_local_memory.py` | LocalMemoryStore tests |
| **Create** | `tests/unit/test_local_experiment_store.py` | Experiment persistence tests |
| **Create** | `tests/unit/test_local_artifact_store.py` | Artifact round-trip tests |
| **Create** | `tests/unit/test_file_tracker.py` | FileTracker tests |
| **Create** | `tests/unit/test_mlflow_tracker.py` | MlflowTracker unit tests |
| **Create** | `tests/unit/test_noop_tracker.py` | NoopTracker tests |
| **Create** | `tests/unit/test_experiment_service.py` | ExperimentService lifecycle tests |
| **Create** | `tests/unit/test_serialization.py` | JSON encoder tests |
| **Create** | `tests/unit/test_settings.py` | Config loading tests |
| **Create** | `tests/unit/test_build_lab.py` | Backend dispatch tests |
| **Create** | `tests/integration/test_mlflow_integration.py` | MLflow end-to-end through Lab |
| **Create** | `tests/integration/test_memory_integration.py` | Memory store through Lab |
| **Create** | `tests/e2e/test_full_lifecycle.py` | Full API lifecycle test |

---

## Implementation Order

| Step | What | Depends On | Est. Effort |
|---|---|---|---|
| 1 | Expand `Settings` + `defaults.py` | — | Small |
| 2 | Create `NoopTracker` | — | Trivial |
| 3 | Create `MlflowTracker` | Step 1 | Medium |
| 4 | Add `close()` to `TrackingConnector` + `FileTracker` | — | Trivial |
| 5 | Rewrite `build_lab()` with dispatch | Steps 1-3 | Medium |
| 6 | Update `stub_agent.py` to write knowledge atoms | — | Small |
| 7 | Add `POST /knowledge`, `DELETE /knowledge/{id}` routes | — | Small |
| 8 | Create tracking router (`GET /tracking/{id}/metrics`) | — | Small |
| 9 | Add lifespan to `app.py`, register tracking router | Steps 4, 8 | Small |
| 10 | Update CLI start banner + config init template | Step 1 | Small |
| 11 | Add `mlflow>=3.0` to `pyproject.toml` | — | Trivial |
| 12 | Write unit tests | Steps 1-10 | Medium |
| 13 | Write integration tests | Steps 1-10 | Medium |
| 14 | Write e2e tests | Steps 1-10 | Medium |
| 15 | Run full test suite, fix issues | Steps 12-14 | Small |

---

## Configuration Examples

### Local PoC (default — no MLflow)

```yaml
# .agentml/config.yaml
tracking:
  backend: "file"
  enabled: true

memory:
  backend: "local"
  search_limit: 10
```

### Local PoC with MLflow

```yaml
# .agentml/config.yaml
tracking:
  backend: "mlflow"
  enabled: true
  mlflow_tracking_uri: "file:./mlruns"
  mlflow_experiment_name: "my-project"

memory:
  backend: "local"
  search_limit: 10
```

### Remote MLflow server

```yaml
tracking:
  backend: "mlflow"
  enabled: true
  mlflow_tracking_uri: "http://mlflow-server:5000"
  mlflow_experiment_name: "production"

memory:
  backend: "local"
```

### Env var override

```bash
AGENTML_TRACKING__BACKEND=mlflow \
AGENTML_TRACKING__MLFLOW_TRACKING_URI=http://mlflow:5000 \
agentml start
```

---

## Acceptance Criteria

1. **`agentml start` with `backend: file`** — works as today, no regressions
2. **`agentml start` with `backend: mlflow`** — starts successfully, creates MLflow experiment, logs metrics/params to MLflow
3. **`agentml start` with `enabled: false`** — tracking calls are silently discarded
4. **`POST /tasks`** — creates experiment, logs to tracker (file or mlflow), creates knowledge atom in memory store
5. **`GET /knowledge`** — returns knowledge atoms created by the agent
6. **`GET /knowledge/relevant?query=...`** — returns keyword-matched atoms
7. **`POST /knowledge`** — creates a knowledge atom via API
8. **`GET /tracking/{id}/metrics`** — returns metrics from configured tracker
9. **Banner** — `agentml start` displays active tracking backend and memory backend
10. **All unit tests pass** — state machine, memory store, experiment store, file tracker, mlflow tracker, noop tracker, settings, build_lab
11. **All integration tests pass** — MLflow full flow, memory store full flow
12. **All e2e tests pass** — full lifecycle with both file and mlflow backends
13. **`mlflow` is optional** — if not installed and backend=mlflow is requested, clear `ImportError` with install instructions
