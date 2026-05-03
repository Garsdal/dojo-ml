# CLAUDE.md — Working in the Dojo.ml repo

> Reference for Claude Code (and me) when making changes here. Optimised for "what do I touch and how" rather than vision/strategy. For vision, see [MASTER_PLAN.md](MASTER_PLAN.md). For the strategic positioning of the project, see the "Positioning" section below.

---

## TL;DR for any change

1. Check this file's [directory map](#directory-map) — file locations follow a strict hexagonal layout.
2. If adding a backend (storage, tracking, agent, compute, sandbox): create the adapter, wire it in [api/deps.py](src/dojo/api/deps.py), add config dispatch, write tests.
3. If adding an agent tool: define a `ToolDef` in [src/dojo/tools/](src/dojo/tools/), include it in [tools/server.py](src/dojo/tools/server.py:16) `collect_all_tools`, update the system prompt in [agents/prompts.py](src/dojo/agents/prompts.py).
4. If adding an API route: create router in [src/dojo/api/routers/](src/dojo/api/routers/), register in [api/app.py](src/dojo/api/app.py), add E2E test, then frontend hook.
5. Run `just test && just lint` before declaring done.

---

## Quick Commands

```bash
just dev              # Install backend + frontend deps (uv sync --all-extras + npm install)
just test             # Run pytest
just lint             # Ruff check + format check
just format           # Auto-fix lint + format
just run              # dojo start (backend + frontend)
just run-stub         # Start with stub agent (no API key)
just run-claude       # Start with Claude agent (uses local claude CLI auth)
just frontend-install # npm install in frontend/
```

---

## Positioning (read this before "improving" things)

Dojo.ml is **not** trying to be a multi-tenant ML platform. It is, today and intentionally:

- **Single-tenant** — one user, one machine, local JSON state in `.dojo/`
- **Bring-your-own-pipeline** — points at a local repo or git URL via `Workspace`
- **Open-core architecture** — execution layer (this repo) is meant to be open. Sandbox cloud, hosted memory, agent reliability layer are *not* built and stay closed when they are.
- **MLflow as bridge, not platform** — `MlflowTracker` sits *on top of* whatever MLflow the user already has, never owns it

Things to **resist** when modifying this repo:
- Adding multi-tenant abstractions (tenant ids, RBAC, SaaS-shaped APIs)
- Adding "enterprise" integration adapters speculatively (Kubeflow, Airflow, Slack, etc.)
- Generalising the storage layer for distributed deployments
- Cloud-execution code paths (until we explicitly start that work)

If a change pulls in any of those, push back or ask first.

---

## Architecture (hexagonal)

```
Settings (YAML + env)  →  build_lab(settings)  →  LabEnvironment (DI container)
                                                        │
CLI (Typer) → create_app(settings) → FastAPI ←──────────┘
                    │                          LabEnvironment {
              Router handlers                    compute, sandbox,
                    │                            experiment_store, artifact_store,
        AgentOrchestrator + Backend              memory_store, tracking,
        (Claude / Stub)                          domain_store, knowledge_link_store,
                    │                            knowledge_linker, settings
        DomainService / ExperimentService      }
        / KnowledgeLinker
                    │
        Adapters (storage / tracking / sandbox / compute)
```

**Composition root:** [api/deps.py:72](src/dojo/api/deps.py#L72) — `build_lab()` builds every adapter and injects them into a single `LabEnvironment` dataclass.

**Single-domain model:** every experiment is scoped to a domain. Every knowledge atom is linked back to the experiment + domain that produced it via `KnowledgeLink`.

---

## Directory Map

| Path | Purpose |
|---|---|
| [src/dojo/core/](src/dojo/core/) | Pure domain models. `Domain`, `DomainTool`, `Workspace`, `Experiment`, `Hypothesis`, `CodeRun`, `KnowledgeAtom`, `KnowledgeLink`, `LinkType`, `ExperimentState`, state-machine transitions. No I/O, no async. |
| [src/dojo/interfaces/](src/dojo/interfaces/) | ABCs (ports). `DomainStore`, `ExperimentStore`, `MemoryStore`, `KnowledgeLinkStore`, `KnowledgeLinker`, `TrackingConnector`, `ComputeBackend`, `Sandbox`, `ArtifactStore`. |
| [src/dojo/storage/local/](src/dojo/storage/local/) | Local JSON adapters: `LocalDomainStore`, `LocalExperimentStore`, `LocalMemoryStore`, `LocalKnowledgeLinkStore`, `LocalArtifactStore`. |
| [src/dojo/tracking/](src/dojo/tracking/) | `FileTracker` (JSON), `MlflowTracker` (MLflow ≥3.0), `NoopTracker`. |
| [src/dojo/sandbox/](src/dojo/sandbox/) | Code execution. `LocalSandbox` (subprocess) — only adapter today. |
| [src/dojo/compute/](src/dojo/compute/) | Compute backends. `LocalCompute` (in-process). |
| [src/dojo/runtime/](src/dojo/runtime/) | `LabEnvironment` (DI dataclass), services that orchestrate the lifecycle: `ExperimentService`, `DomainService`, `WorkspaceService`, `WorkspaceScanner`, `KeywordKnowledgeLinker`. |
| [src/dojo/agents/](src/dojo/agents/) | Agent orchestration. `AgentBackend` ABC + `claude.py` / `stub.py` implementations. `AgentOrchestrator`, `AgentRun`, `AgentEvent`, system prompts. |
| [src/dojo/tools/](src/dojo/tools/) | Agent tool definitions (MCP). `experiments.py`, `knowledge.py`, `tracking.py`, `domain_tools.py`, `tool_generation.py`. Adapter in `tools/adapters/claude.py` converts `ToolDef` → MCP server. |
| [src/dojo/api/](src/dojo/api/) | FastAPI app. `app.py` builds the app; `deps.py` builds `LabEnvironment`; `routers/` holds one file per resource. |
| [src/dojo/cli/](src/dojo/cli/) | Typer CLI: `start`, `run`, `domain`, `config`. |
| [src/dojo/config/](src/dojo/config/) | `Settings` (pydantic-settings), `defaults.py`, YAML loading. |
| [src/dojo/utils/](src/dojo/utils/) | `generate_id()` (ULID), JSON serialization, `structlog` setup. |
| [frontend/](frontend/) | React 19 + Vite 7 + shadcn/ui. Proxies `/api` → `:8000`. **Currently de-prioritised** — solidify backend first. |
| [tests/](tests/) | `unit/`, `integration/`, `e2e/`. `conftest.py` builds a real `LabEnvironment` against a tmp dir — no mocking. |

---

## Core Domain Model

### Domain → Experiment → Knowledge

```
Domain (human-defined)
  ├── Workspace (local repo / git url / empty dir)
  ├── DomainTools (semantic hints + optional executable tools)
  └── Experiments (agent-created)
        ├── Hypothesis
        ├── CodeRuns (each run_experiment_code call)
        └── ExperimentResult (metrics, artifacts, logs, error)
              └── produces KnowledgeAtoms via KnowledgeLinker
                    └── linked via KnowledgeLink (CREATED_BY, RELATED_TO)
```

### State machine

`ExperimentState`: `PENDING → RUNNING → COMPLETED | FAILED → ARCHIVED`. Invalid transitions raise `InvalidTransitionError` from [core/state_machine.py](src/dojo/core/state_machine.py).

`DomainStatus`: `DRAFT → ACTIVE → PAUSED → COMPLETED → ARCHIVED`.

`RunStatus` (agent): `PENDING → RUNNING → COMPLETED | FAILED | STOPPED`.

### Knowledge linking — current behaviour

Every `write_knowledge` call goes through [runtime/keyword_linker.py](src/dojo/runtime/keyword_linker.py). The linker:

1. Always creates a new immutable atom (no merging).
2. Searches for similar atoms via keyword overlap (≥40% of smaller word set, ≥3 overlapping words).
3. Records a `CREATED_BY` link to the experiment + domain.
4. Records `RELATED_TO` links to similar atoms.

This is intentionally simple. An agentic linker is a planned alternative — slot it behind the same `KnowledgeLinker` interface in [interfaces/knowledge_linker.py](src/dojo/interfaces/knowledge_linker.py).

---

## Agent System

### Backends

`AgentBackend` ([agents/backend.py](src/dojo/agents/backend.py)) — abstract. Two implementations:

- **`ClaudeAgentBackend`** — uses `ClaudeSDKClient` from `claude-agent-sdk`. Tools served via MCP. Inherits the user's local `claude` CLI auth (no API key needed for runs).
- **`StubAgent`** — deterministic mock for offline / CI runs.

`create_agent_backend(settings)` in [agents/factory.py](src/dojo/agents/factory.py) dispatches on `settings.agent.backend` (`"claude"` | `"stub"`).

### Run lifecycle

[agents/orchestrator.py](src/dojo/agents/orchestrator.py):

```
orchestrator.start(prompt, domain_id) →
  load Domain + accumulated knowledge →
  build_system_prompt(run, domain, accumulated_knowledge) →
  collect_all_tools(lab, domain) →
  backend.configure(tools, config) →
  return AgentRun

orchestrator.execute(run) → async iterate backend.execute() → append events to run.events
orchestrator.stop()      → backend.stop() + transition to STOPPED
```

Events are streamed to the frontend via SSE at `/agent/runs/{id}/events`. Run state is held in-memory in `_runs` (see [api/routers/agent.py:19](src/dojo/api/routers/agent.py#L19)) — note: not persisted across server restarts. Run *persistence* on disk just landed (commit `95faee5`); confirm what state the in-memory dict is in before relying on it.

### Tools the agent has

| Tool | Purpose | File |
|---|---|---|
| `create_experiment` | Register a new experiment with hypothesis. State → RUNNING. | [tools/experiments.py](src/dojo/tools/experiments.py) |
| `run_experiment_code` | Execute Python in the workspace. Stores code as artifact, records `CodeRun`. | [tools/experiments.py](src/dojo/tools/experiments.py) |
| `complete_experiment` / `fail_experiment` | Transition state, log metrics. | [tools/experiments.py](src/dojo/tools/experiments.py) |
| `get_experiment` / `list_experiments` / `compare_experiments` | Read-side. | [tools/experiments.py](src/dojo/tools/experiments.py) |
| `write_knowledge` | Routes through `KnowledgeLinker.produce_knowledge`. Cannot bypass linker. | [tools/knowledge.py](src/dojo/tools/knowledge.py) |
| `search_knowledge` / `list_knowledge` | Read knowledge with optional `domain_id` filter. | [tools/knowledge.py](src/dojo/tools/knowledge.py) |
| `log_metrics` / `log_params` | Write to the active `TrackingConnector`. | [tools/tracking.py](src/dojo/tools/tracking.py) |
| Domain executable tools | Per-domain tools with `executable=True` are registered as MCP tools at run-start. Tools with `executable=False` appear as semantic hints in the system prompt. | [tools/domain_tools.py](src/dojo/tools/domain_tools.py), [agents/prompts.py](src/dojo/agents/prompts.py) |

### Built-in Claude tools also allowed

`Bash`, `Read`, `Write`, `Edit`, `WebFetch` (see [agents/backends/claude.py:17](src/dojo/agents/backends/claude.py#L17)). Bash is permitted, but the system prompt instructs the agent to use `run_experiment_code` instead for experiment scripts so we get artifact traceability.

---

## Workspaces

A `Workspace` ([core/domain.py:38](src/dojo/core/domain.py#L38)) is a per-domain pre-configured execution environment. One-time setup happens via `WorkspaceService.setup(domain)` ([runtime/workspace_service.py](src/dojo/runtime/workspace_service.py)), then every agent run reuses it.

Sources:
- **`local`** — point at an existing path on disk
- **`git`** — clone a repo into `.dojo/workspaces/{domain_id}` (optionally checking out a ref)
- **`empty`** — create a fresh empty dir

Setup auto-detects:
1. Existing `.venv` / `venv` → reuse
2. `pyproject.toml` → `uv sync` (preferred) or `pip install -e .`
3. `requirements.txt` → create venv + `pip install -r`
4. Else → system Python

The agent's `cwd` and `python_path` are pinned to the workspace at run-start ([agents/orchestrator.py:103-108](src/dojo/agents/orchestrator.py#L103-L108)). The system prompt explicitly tells the agent **not** to install packages or set up environments — they're already there.

This is the "bring your own Python pipeline" hook. Prefer modifying the workspace abstraction over building parallel integration mechanisms.

---

## API Surface

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | `{"status": "ok"}` |
| `POST` | `/domains` | Create domain (name, prompt, tools, workspace) |
| `GET` | `/domains` / `/domains/{id}` | List / get |
| `PUT` | `/domains/{id}` | Update fields |
| `DELETE` | `/domains/{id}` | Delete |
| `POST` | `/domains/{id}/tools` | Add a domain tool |
| `GET` | `/domains/{id}/tools` | List domain tools |
| `DELETE` | `/domains/{id}/tools/{tool_id}` | Remove a domain tool |
| `POST` | `/domains/{id}/tools/generate` | AI-generate tool definitions (returns suggestions, doesn't auto-register) |
| `POST` | `/domains/{id}/workspace/setup` | Trigger one-time workspace setup |
| `GET` | `/domains/{id}/workspace/status` | Workspace readiness |
| `POST` | `/domains/{id}/workspace/validate` | Sanity-check the python env |
| `POST` | `/domains/{id}/workspace/scan` | Scan files, return tool suggestions |
| `GET` | `/domains/{id}/experiments` | List experiments for domain |
| `GET` | `/domains/{id}/metrics` | Metric evolution across experiments |
| `GET` | `/domains/{id}/knowledge` | Knowledge atoms linked to domain |
| `GET` | `/experiments` / `/experiments/{id}` | List / get (optional `?domain_id=`) |
| `GET` | `/knowledge` / `/knowledge/{id}` | List / get atoms |
| `POST` | `/knowledge` | Direct atom creation (still goes through linker) |
| `DELETE` | `/knowledge/{id}` | Delete atom |
| `POST` | `/agent/run` | Start agent run on a domain |
| `GET` | `/agent/runs` / `/agent/runs/{id}` | List / get runs |
| `POST` | `/agent/runs/{id}/stop` | Stop a running agent |
| `GET` | `/agent/runs/{id}/events` | SSE event stream |
| `GET` | `/tracking/{experiment_id}/metrics` | Per-experiment tracked metrics |
| `GET` | `/config` | Public config summary |

Frontend hooks live in [frontend/src/hooks/](frontend/src/hooks/) and follow `use-{resource}.ts` naming.

---

## Config System

YAML at `.dojo/config.yaml`, overridable via env vars. See [config/settings.py](src/dojo/config/settings.py).

| Group | Key fields | Defaults |
|---|---|---|
| `api` | `host`, `port` | `127.0.0.1:8000` |
| `storage` | `base_dir` | `.dojo` |
| `tracking` | `backend`, `enabled`, `mlflow_tracking_uri`, `mlflow_experiment_name`, `mlflow_artifact_location` | `file`, `true` |
| `memory` | `backend`, `search_limit` | `local`, `10` |
| `llm` | `provider`, `model`, `api_key` | `stub`, `stub` |
| `frontend` | `enabled`, `port` | `true`, `5173` |
| `sandbox` | `timeout` | `30.0` |
| `agent` | `backend`, `max_turns`, `max_budget_usd`, `permission_mode`, `cwd` | `claude`, `50`, `None`, `acceptEdits`, `None` |

### Environment variable gotcha

Pydantic-settings prefix is `DOJO_` (single trailing underscore). Nested fields use `__` (double underscore). One underscore between `DOJO` and the top-level field, two between nested fields:

```
✅ DOJO_AGENT__BACKEND=stub
✅ DOJO_TRACKING__BACKEND=mlflow
❌ DOJO__AGENT__BACKEND=stub      ← silently ignored
```

Pydantic-settings **silently ignores misspelled env vars** — defaults kick in with no warning. Always double-check the underscore count if overrides aren't sticking.

---

## Testing

```bash
just test                         # all
uv run pytest tests/unit/ -v      # unit only
uv run pytest tests/e2e/ -v       # E2E (HTTP lifecycle)
uv run pytest tests/integration/ -v
```

**Config:** `asyncio_mode = "auto"` in [pyproject.toml](pyproject.toml) — all `async def test_*` are auto-detected. `pythonpath = ["src"]`.

**Fixtures** ([tests/conftest.py](tests/conftest.py)): `settings(tmp_dir)` builds a `Settings` pointing at a temp dir; `lab(settings)` builds a real `LabEnvironment` with real adapters; `client(settings)` returns an httpx `AsyncClient` on the ASGI app. **No mocking** — everything runs against real adapters in tmp dirs. Match this pattern when adding tests.

**Patterns:** `pytest.raises(InvalidTransitionError)`, `pytest.approx(0.95)`, async CRUD round-trips, HTTP status assertions via `client.get/post/delete`.

---

## Recipes

### Adding a new storage backend (e.g. Postgres)

1. Create `src/dojo/storage/postgres/` mirroring `local/` (artifact, domain, experiment, knowledge_link, memory).
2. Each adapter implements its ABC from [src/dojo/interfaces/](src/dojo/interfaces/).
3. Add dispatch in [api/deps.py](src/dojo/api/deps.py) — pick which adapter set to instantiate based on `settings.storage.backend`.
4. Extend `StorageSettings` in [config/settings.py](src/dojo/config/settings.py) with whatever connection fields are needed.
5. Add unit tests for adapter round-trips in `tests/unit/`. Add an integration test wiring the new adapter through `LabEnvironment`.
6. Don't break existing local imports — re-export from `storage/__init__.py` if needed.

### Adding a new agent backend

1. Implement `AgentBackend` in `src/dojo/agents/backends/<name>.py` (`configure`, `execute`, `stop`, `complete`, `name`).
2. Add it to the dispatch in [agents/factory.py](src/dojo/agents/factory.py).
3. If it needs a different tool format, write an adapter in `tools/adapters/` (mirroring `claude.py`).
4. Extend `AgentSettings.backend` enum implicitly by accepting the new string in factory.
5. Tests: stub-style mocks of the SDK, plus an E2E that runs `/agent/run` end-to-end.

### Adding a new agent tool

1. Add a function in `src/dojo/tools/<resource>.py` that returns a `ToolDef` (or extend an existing factory like `create_experiment_tools`).
2. Wire it into [tools/server.py](src/dojo/tools/server.py:16) `collect_all_tools` so it's registered for every run.
3. Update the system prompt in [agents/prompts.py](src/dojo/agents/prompts.py) so the agent knows the tool exists.
4. Test the tool directly (round-trip) and via an agent run if non-trivial.

### Adding a new API route

1. Create `src/dojo/api/routers/<name>.py` with `APIRouter(prefix=..., tags=...)`.
2. Access lab via `request.app.state.lab: LabEnvironment`.
3. Register in [api/app.py](src/dojo/api/app.py) with `app.include_router(...)`.
4. Add an E2E test in `tests/e2e/`.
5. Add a hook in `frontend/src/hooks/` if the UI needs it.

### Adding a tracking backend

Mirror the existing dispatch in `_build_tracking()` in [api/deps.py](src/dojo/api/deps.py:23). The `TrackingConnector` interface is small (see [interfaces/tracking.py](src/dojo/interfaces/tracking.py)).

---

## Conventions

- **IDs:** ULIDs via `dojo.utils.ids.generate_id()`. Never use uuid4.
- **Async everywhere:** all interface methods, all service methods, all router handlers.
- **Domain models:** `@dataclass`. **API request/response:** `pydantic.BaseModel`.
- **No global state:** everything flows through `LabEnvironment` injected at app startup. Don't add module-level singletons.
- **Logging:** `structlog` via `from dojo.utils.logging import get_logger`. Use structured kwargs (`logger.info("event_name", key=value)`), not f-strings.
- **Linting:** Ruff (`py313`, line-length 100, rules `E,F,W,I,UP,B,SIM,RUF`). Run `just format` before committing.
- **Errors:** raise specific exceptions (`InvalidTransitionError`, `ValueError`) at boundaries; let them bubble to the router which translates to HTTP.
- **No silent fallbacks:** if a config is wrong, fail loud at `build_lab()` time. Don't paper over with try/except.
- **Single-tenant assumption:** writing code that requires a tenant or user id is a smell — push back.

---

## Open questions / known issues

- **Run state in-memory + on-disk** — `_runs` dict in [api/routers/agent.py:19](src/dojo/api/routers/agent.py#L19) is now a write-through cache over `LabEnvironment.run_store` (`LocalRunStore` writes to `.dojo/runs/{id}.json`). `GET /agent/runs/{id}` and the SSE stream fall back to disk on cache miss, so two processes (CLI + server) see each other's runs.
- **AGENTS.md is gone** — was stale; this CLAUDE.md is the source of truth.
- **`docs/`** has been cleaned — only `archive/end-to-end-agent-harness-v2.md` remains as historical reference. Don't trust archived docs without cross-checking the code.
- **Task contract enforced (Phase 3 done)** — [runtime/tool_verifier.py](src/dojo/runtime/tool_verifier.py) runs tools against their `ToolContract`; [runtime/task_service.py](src/dojo/runtime/task_service.py) `freeze` rejects unless every required tool's `verification.verified is True` (override: `skip_verification=True`); the orchestrator calls `assert_ready` before configuring the backend. `complete_experiment` ([tools/experiments.py](src/dojo/tools/experiments.py)) rejects metric keys outside `task.config["expected_metrics"]` (auto-seeded from the registry's evaluator contract).
- **`Domain.tools` still exists alongside `domain.task.tools`** — Phase 3 made `domain.task.tools` the source of truth (`collect_all_tools` reads from there when a task is set, with `domain.tools` as a legacy fallback). `Domain.tools` is mirrored on writes for the existing frontend response; the field will be removed in the Phase 5 frontend audit.
- **`task_id` legacy in frontend** — fully cleaned in Phase 0. `use-experiments.ts` now uses `domainId`/`?domain_id=`.
