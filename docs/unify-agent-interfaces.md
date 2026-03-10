# Unify Agent Interfaces — StubAgent → AgentBackend

> **Goal:** Replace the old `Agent` ABC + `StubAgent` with the v2 `AgentBackend` event framework, so the stub backend emits `AgentEvent`s through the same pipeline as the Claude backend.

## Current State

Two separate agent abstractions:

| | Old: `Agent` ABC | New: `AgentBackend` ABC |
|---|---|---|
| File | `interfaces/agent.py` | `agents/backend.py` |
| Method | `run(task, lab) → TaskResult` | `configure() + execute(prompt) → AsyncIterator[AgentEvent]` |
| Implementation | `StubAgent` (hardcoded experiment flow) | `ClaudeAgentBackend`, `StubAgentBackend` |
| Used by | `POST /tasks` (tasks router) | `POST /agent/run` (agent router) |
| Output | `TaskResult` (batch, opaque) | Stream of `AgentEvent`s (live, observable) |

The `StubAgent` directly calls `lab.experiment_store`, `lab.tracking`, and `lab.memory_store` — bypassing the MCP tools entirely. This means it doesn't test the tool layer at all.

## Target State

One agent abstraction: `AgentBackend`. The stub backend replays a realistic sequence of `AgentEvent`s that mirror what the Claude backend would produce — including tool calls to the v1 MCP tools.

```
POST /tasks  ───┐
                 ├──→  AgentOrchestrator  ──→  AgentBackend
POST /agent/run ─┘          │                    ├── ClaudeAgentBackend
                            │                    └── StubAgentBackend (emits events)
                            │
                         ToolDefs (v1) ← tools actually execute
```

## Changes

### Step 1 — Rewrite `StubAgentBackend` to use MCP tools (~1 hour)

Currently planned as a thin "yield canned events" stub. Instead, make it a **local simulation** that actually calls the v1 `ToolDef` handlers:

**File:** `src/agentml/agents/backends/stub.py`

```python
class StubAgentBackend(AgentBackend):
    """Runs a scripted experiment flow using real ToolDef handlers.

    Simulates what a real agent would do:
    1. search_knowledge
    2. create_experiment
    3. complete_experiment with mock metrics
    4. write_knowledge
    5. yield a result event

    Each step emits tool_call + tool_result events, so the UI
    and SSE pipeline see the same event shapes as with Claude.
    """

    def __init__(self) -> None:
        self._tool_defs: list[ToolDef] = []
        self._config: AgentRunConfig | None = None
        self._tools_by_name: dict[str, ToolDef] = {}

    async def configure(self, tool_defs, config) -> None:
        self._tool_defs = tool_defs
        self._config = config
        self._tools_by_name = {t.name: t for t in tool_defs}

    async def execute(self, prompt: str) -> AsyncIterator[AgentEvent]:
        # Helper to call a tool and yield events
        async def call_tool(name: str, params: dict) -> Any:
            yield AgentEvent(event_type="tool_call", data={"tool": name, "input": params})
            tool = self._tools_by_name[name]
            result = await tool.handler(**params)
            yield AgentEvent(event_type="tool_result", data={"tool": name, "output": result.data})
            return result

        # 1. Text: announce plan
        yield AgentEvent(event_type="text", data={"text": f"Planning stub experiment for: {prompt}"})

        # 2. Search knowledge
        async for event in call_tool("search_knowledge", {"query": prompt, "limit": 5}):
            yield event

        # 3. Create experiment
        async for event in call_tool("create_experiment", {
            "task_id": <extracted from config>,
            "hypothesis": f"Stub hypothesis for: {prompt}",
            "config": {"model": "stub"},
        }):
            yield event
        experiment_id = <from result>

        # 4. Complete experiment with mock metrics
        async for event in call_tool("complete_experiment", {
            "experiment_id": experiment_id,
            "metrics": {"accuracy": 0.95, "f1_score": 0.93},
        }):
            yield event

        # 5. Log metrics
        async for event in call_tool("log_metrics", {
            "experiment_id": experiment_id,
            "metrics": {"accuracy": 0.95, "f1_score": 0.93},
        }):
            yield event

        # 6. Write knowledge
        async for event in call_tool("write_knowledge", {
            "context": f"Task: {prompt}",
            "claim": "Stub model achieves 95% accuracy on test data.",
            "confidence": 0.85,
            "evidence_ids": [experiment_id],
        }):
            yield event

        # 7. Result
        yield AgentEvent(event_type="result", data={
            "session_id": None,
            "turns": 6,
            "cost_usd": 0.0,
            "duration_ms": 100,
            "is_error": False,
        })

    async def stop(self) -> None:
        pass  # Stub finishes instantly
```

**Key difference from the current `StubAgent`:** Instead of directly calling `lab.experiment_store.save()`, it calls the same `ToolDef.handler()` functions that the Claude backend would invoke via MCP. This means the tools layer is actually exercised.

### Step 2 — Rewrite `POST /tasks` to use `AgentOrchestrator` (~30 min)

The tasks router currently hardcodes `StubAgent()`. Rewrite it to go through the same orchestrator path:

**File:** `src/agentml/api/routers/tasks.py`

```python
@router.post("", response_model=TaskResponse)
async def create_task(body: CreateTaskRequest, request: Request) -> TaskResponse:
    lab = _get_lab(request)
    settings = request.app.state.settings

    # Use the same AgentOrchestrator + backend as /agent/run
    backend = create_agent_backend(settings.agent.backend)
    orchestrator = AgentOrchestrator(lab, backend, max_turns=settings.agent.max_turns)

    run = await orchestrator.start(prompt=body.prompt)
    await orchestrator.execute(run)  # Synchronous — wait for completion

    # Build response from the run's events and the experiment store
    ...
```

This means `POST /tasks` and `POST /agent/run` share the exact same pipeline. The only difference: `/tasks` awaits completion synchronously, `/agent/run` spawns a background task and streams events via SSE.

### Step 3 — Delete the old `Agent` ABC and `StubAgent` (~15 min)

| Delete | Reason |
|---|---|
| `src/agentml/interfaces/agent.py` | Replaced by `agents/backend.py` (`AgentBackend` ABC) |
| `src/agentml/agents/stub_agent.py` | Replaced by `agents/backends/stub.py` (`StubAgentBackend`) |

Update `src/agentml/interfaces/__init__.py` to remove the `Agent` re-export.

### Step 4 — Update v2 plan section 2.4 (~5 min)

Replace the "keep them separate" note with:

> The old `Agent` ABC and `StubAgent` have been unified into `AgentBackend`. The `StubAgentBackend` replays a scripted experiment flow using real `ToolDef` handlers, emitting the same `AgentEvent` stream as the Claude backend. Both `POST /tasks` and `POST /agent/run` go through the `AgentOrchestrator`.

### Step 5 — Update tests (~30 min)

| Test file | Change |
|---|---|
| `tests/e2e/test_full_lifecycle.py` | `POST /tasks` now goes through orchestrator — assertions on events |
| `tests/unit/test_agent_backend.py` | Test `StubAgentBackend` calls tool handlers and yields correct event types |
| `tests/unit/test_orchestrator.py` | Orchestrator tests already use `StubAgentBackend` — verify events append to `AgentRun.events` |

## What This Achieves

1. **One abstraction** — `AgentBackend` is the only agent interface
2. **Stub tests the real tools** — `StubAgentBackend` calls `ToolDef.handler()`, not `lab.*` directly
3. **Unified pipeline** — both `/tasks` and `/agent/run` go through `AgentOrchestrator`
4. **UI works with stub** — set `agent.backend=stub`, see real events in the event feed
5. **No dead code** — old `Agent` ABC and `StubAgent` are removed

## Estimated Time

| Step | Time |
|---|---|
| 1. Rewrite StubAgentBackend | ~1 hour |
| 2. Rewrite tasks router | ~30 min |
| 3. Delete old interfaces | ~15 min |
| 4. Update v2 plan | ~5 min |
| 5. Update tests | ~30 min |
| **Total** | **~2.5 hours** |
