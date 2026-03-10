# AGENTS.md — AgentML Codebase Reference

> **AgentML** — AI-powered ML experiment orchestration with a hexagonal (ports & adapters) architecture.
> Python 3.13+, FastAPI backend, React/TypeScript frontend, config-driven backend selection.

## Quick Commands

```bash
just dev              # Install all deps (uv sync --all-extras)
just test             # Run pytest
just lint             # Ruff check + format check
just format           # Auto-fix lint + format
just run              # agentml start (backend + frontend)
just run-stub         # Start with stub agent (no API key)
just frontend-install # npm install in frontend/
```

## Architecture

```
Settings (YAML + env vars)  →  build_lab(settings)  →  LabEnvironment (DI container)
                                                            │
CLI (Typer) → create_app(settings) → FastAPI ←──────────────┘
                    │                                  LabEnvironment {
              Router handlers                            compute:          ComputeBackend
                    │                                    sandbox:          Sandbox
         StubAgent.run(task, lab)                        experiment_store: ExperimentStore
                    │                                    artifact_store:   ArtifactStore
         ExperimentService                               memory_store:     MemoryStore
         (state machine transitions)                     tracking:         TrackingConnector
                                                       }
```

**Composition root:** `src/agentml/api/deps.py` → `build_lab()` dispatches on `settings.tracking.backend` and `settings.memory.backend`.

## Directory Map

| Directory | Purpose |
|---|---|
| `src/agentml/core/` | Pure domain: `Experiment`, `Task`, `KnowledgeAtom`, `ExperimentState` enum, state machine transitions |
| `src/agentml/interfaces/` | ABCs (ports): `Agent`, `ComputeBackend`, `Sandbox`, `ExperimentStore`, `ArtifactStore`, `MemoryStore`, `TrackingConnector`, `ToolRuntime` |
| `src/agentml/agents/` | Agent implementations. Currently: `StubAgent` (mock, no LLM) |
| `src/agentml/compute/` | Compute backends. Currently: `LocalCompute` (in-process) |
| `src/agentml/sandbox/` | Code execution. Currently: `LocalSandbox` (subprocess) |
| `src/agentml/storage/` | Persistence adapters: `LocalExperimentStore` (JSON), `LocalArtifactStore` (files), `LocalMemoryStore` (JSON keyword search) |
| `src/agentml/tracking/` | Experiment tracking: `FileTracker` (JSON), `MlflowTracker` (MLflow ≥3.0), `NoopTracker` |
| `src/agentml/runtime/` | `LabEnvironment` (DI dataclass), `ExperimentService` (lifecycle orchestration) |
| `src/agentml/api/` | FastAPI app + routers. `app.py` creates app, `deps.py` builds lab |
| `src/agentml/cli/` | Typer CLI: `start`, `run`, `config init/show` |
| `src/agentml/config/` | `Settings` (pydantic-settings), `defaults.py`, YAML loading |
| `src/agentml/utils/` | `generate_id()` (ULID), JSON serialization, structlog setup |
| `frontend/` | React 19 + Vite 7 + shadcn/ui dark theme. Proxies `/api` → backend `:8000` |

## API Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/health` | `{"status":"ok"}` |
| POST | `/tasks` | Create + run task `{"prompt":"..."}` → `TaskResponse` |
| GET | `/tasks`, `/tasks/{id}` | List / get tasks (in-memory, not persisted) |
| GET | `/experiments`, `/experiments/{id}` | List / get experiments (optional `?task_id=` filter) |
| GET | `/knowledge` | List all knowledge atoms |
| GET | `/knowledge/relevant?query=&limit=` | Keyword search knowledge |
| POST | `/knowledge` | Create atom `{context, claim, action?, confidence?, evidence_ids?}` → 201 |
| DELETE | `/knowledge/{id}` | Delete atom → 204 |
| GET | `/tracking/{experiment_id}/metrics` | Get tracked metrics |
| GET | `/config` | Public config summary |

## State Machine

`ExperimentState`: PENDING → RUNNING → COMPLETED/FAILED → ARCHIVED. Invalid transitions raise `InvalidTransitionError`.

## Config System

YAML at `.agentml/config.yaml`, overridable via env vars (`AGENTML__TRACKING__BACKEND=mlflow`).

| Setting | Key fields | Defaults |
|---|---|---|
| `api` | `host`, `port` | `127.0.0.1:8000` |
| `storage` | `base_dir` | `.agentml` |
| `tracking` | `backend`, `enabled`, `mlflow_tracking_uri`, `mlflow_experiment_name` | `file`, `true` |
| `memory` | `backend`, `search_limit` | `local`, `10` |
| `llm` | `provider`, `model`, `api_key` | `stub`, `stub` |
| `frontend` | `enabled`, `port` | `true`, `5173` |
| `sandbox` | `timeout` | `30.0` |

## Testing

```bash
just test                          # All tests
uv run pytest tests/unit/ -v      # Unit only
uv run pytest tests/e2e/ -v       # E2E (HTTP lifecycle)
```

**Config:** `asyncio_mode = "auto"`, `pythonpath = ["src"]` — all `async def test_*` auto-detected.

**Fixtures** (`tests/conftest.py`): `settings(tmp_dir)` → temp `Settings`; `lab(settings)` → real `LabEnvironment`; `client(settings)` → httpx `AsyncClient` on ASGI app. No mocking — tests use real adapters against temp dirs.

**Test patterns:** `pytest.raises(InvalidTransitionError)`, `pytest.approx(0.95)`, async CRUD round-trips, HTTP status assertions via `client.get/post/delete`.

## Adding a New Backend

1. **Create adapter** in the matching directory (e.g., `src/agentml/storage/postgres_experiment.py`)
2. **Implement the interface** from `src/agentml/interfaces/`
3. **Wire in `build_lab()`** (`src/agentml/api/deps.py`) — add dispatch case for the new `backend` string
4. **Add config fields** if needed to `src/agentml/config/settings.py`
5. **Add tests** in `tests/unit/` (adapter round-trip) and `tests/integration/` (through LabEnvironment)

## Adding a New API Route

1. Create router in `src/agentml/api/routers/` with `APIRouter(prefix="/...", tags=[...])`
2. Access lab via `request.app.state.lab: LabEnvironment`
3. Register in `src/agentml/api/app.py`: `app.include_router(router)`
4. Add E2E test in `tests/e2e/test_full_lifecycle.py`
5. Add frontend hook in `frontend/src/hooks/` and page/component as needed

## Key Conventions

- **IDs**: ULIDs via `agentml.utils.ids.generate_id()`
- **Async everywhere**: All interface methods and service methods are `async`
- **Dataclasses** for domain models, **pydantic BaseModel** for API request/response schemas
- **No global state**: Everything flows through `LabEnvironment` injected at app startup
- **Logging**: `structlog` via `get_logger(__name__)`
- **Linting**: Ruff (`py313`, line-length 100, rules: `E,F,W,I,UP,B,SIM,RUF`)
