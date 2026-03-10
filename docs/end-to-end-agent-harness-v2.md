# End-to-End Agent Harness v2 — Agent Sessions, API & UI

> **Prerequisite:** v1 is complete — AgentML MCP tools exist and work with Claude Agent SDK.
>
> **Goal:** Wire the agent into the FastAPI backend so users can start, monitor, and stop ML research sessions from the UI.

---

## Key Design Principle: Claude Code Does the Heavy Lifting

From the Claude Agent SDK docs, we use:

| SDK Feature | What it gives us | Our usage |
|---|---|---|
| `ClaudeSDKClient` | Persistent session, multi-turn conversation, interrupt support | One client per agent run — supports follow-up and stop |
| `@tool` + `create_sdk_mcp_server()` | Custom MCP tools | Our AgentML tools from v1 |
| `ClaudeAgentOptions` | System prompt, permissions, max_turns, budget, cwd, hooks | Full agent configuration |
| Hooks (`PreToolUse`, `PostToolUse`) | Intercept every tool call | Event streaming to UI |
| `ResultMessage` | Cost, duration, turns, session_id | Run summary & cost tracking |
| `AssistantMessage` / `ToolUseBlock` | Real-time message stream | Event feed in UI |
| `include_partial_messages` | Streaming events | Low-latency UI updates |
| `max_turns` / `max_budget_usd` | Safety limits | Prevent runaway agents |
| `client.interrupt()` | Stop the agent mid-task | Stop button in UI |
| Built-in tools (`Bash`, `Write`, etc.) | Code execution, file I/O | Agent writes & runs ML code |

**We are a thin orchestration layer:**

```
UI → POST /agent/run → AgentOrchestrator
                            │
                            ├── Build LabEnvironment (existing)
                            ├── Create AgentML MCP server (v1)
                            ├── Configure ClaudeSDKClient (system prompt, tools, hooks)
                            ├── Launch background task
                            │     └── client.query(prompt) + receive_messages()
                            ├── Stream events via SSE
                            └── Support interrupt via client.interrupt()
```

---

## Table of Contents

1. [Architecture](#1-architecture)
2. [Agent Orchestrator](#2-agent-orchestrator)
3. [System Prompt Design](#3-system-prompt-design)
4. [API Routes](#4-api-routes)
5. [Event Streaming](#5-event-streaming)
6. [Frontend Changes](#6-frontend-changes)
7. [Configuration](#7-configuration)
8. [Task-Level Tool Hints](#8-task-level-tool-hints)
9. [File-by-File Change Map](#9-file-by-file-change-map)
10. [Implementation Steps](#10-implementation-steps)
11. [End-to-End Example: Boston Housing](#11-end-to-end-example-boston-housing)

---

## 1. Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                        Frontend (React)                       │
│                                                               │
│  Agent Page                                                   │
│  ├── Prompt form + tool hints                                │
│  ├── "Start Research" button                                 │
│  ├── Live event feed (SSE)                                   │
│  ├── Experiment cards (auto-updating)                        │
│  ├── Knowledge feed                                          │
│  └── "Stop Agent" button                                     │
│                                                               │
└──────────────────┬───────────────────────────────────────────┘
                   │  REST + SSE
┌──────────────────▼───────────────────────────────────────────┐
│                     FastAPI Backend                            │
│                                                               │
│  POST /agent/run         → start agent session                │
│  GET  /agent/runs        → list runs                          │
│  GET  /agent/runs/{id}   → get run status                     │
│  GET  /agent/runs/{id}/events → SSE stream                    │
│  POST /agent/runs/{id}/stop   → interrupt agent               │
│                                                               │
│  AgentOrchestrator (per run)                                  │
│  ├── ClaudeSDKClient (claude-agent-sdk)                      │
│  │   ├── system_prompt (AgentML researcher prompt)           │
│  │   ├── mcp_servers: {"agentml": our_server}                │
│  │   ├── allowed_tools: [AgentML + Bash + Read + Write]      │
│  │   ├── hooks: {PreToolUse: [logger], PostToolUse: [logger]}│
│  │   ├── permission_mode: "acceptEdits"                      │
│  │   ├── max_turns: 50                                        │
│  │   ├── max_budget_usd: 1.00                                │
│  │   └── cwd: sandbox working directory                      │
│  └── Event buffer → SSE endpoints                             │
│                                                               │
│  LabEnvironment (unchanged from v1)                           │
│  ├── experiment_store                                         │
│  ├── memory_store                                             │
│  ├── tracking                                                 │
│  └── artifact_store                                           │
└───────────────────────────────────────────────────────────────┘
```

---

## 2. Agent Orchestrator

**File:** `src/agentml/agents/orchestrator.py`

The orchestrator manages a single agent run's lifecycle. It's not an "agent" itself — it wraps `ClaudeSDKClient`.

```python
"""Agent orchestrator — manages a Claude Code session for an AgentML task."""

import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ResultMessage,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
)

from agentml.runtime.lab import LabEnvironment
from agentml.tools.server import create_agentml_server
from agentml.utils.ids import generate_id
from agentml.utils.logging import get_logger

logger = get_logger(__name__)


class RunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    STOPPED = "stopped"


@dataclass
class AgentEvent:
    """A single event in the agent run timeline."""
    id: str = field(default_factory=generate_id)
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    event_type: str = ""           # tool_call, tool_result, text, error, status_change
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentRun:
    """State of a single agent run."""
    id: str = field(default_factory=generate_id)
    task_id: str = ""
    prompt: str = ""
    status: RunStatus = RunStatus.PENDING
    events: list[AgentEvent] = field(default_factory=list)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    session_id: str | None = None
    total_cost_usd: float | None = None
    num_turns: int = 0
    error: str | None = None


# All allowed AgentML tools (prefixed for MCP)
AGENTML_TOOLS = [
    "mcp__agentml__create_experiment",
    "mcp__agentml__complete_experiment",
    "mcp__agentml__fail_experiment",
    "mcp__agentml__get_experiment",
    "mcp__agentml__list_experiments",
    "mcp__agentml__compare_experiments",
    "mcp__agentml__write_knowledge",
    "mcp__agentml__search_knowledge",
    "mcp__agentml__list_knowledge",
    "mcp__agentml__log_metrics",
    "mcp__agentml__log_params",
]

# Claude Code built-in tools the agent may use
BUILTIN_TOOLS = ["Bash", "Read", "Write", "Edit", "WebFetch"]


class AgentOrchestrator:
    """Manages one agent run using ClaudeSDKClient."""

    def __init__(
        self,
        lab: LabEnvironment,
        *,
        max_turns: int = 50,
        max_budget_usd: float | None = None,
        cwd: str | None = None,
    ) -> None:
        self.lab = lab
        self.max_turns = max_turns
        self.max_budget_usd = max_budget_usd
        self.cwd = cwd
        self._client: ClaudeSDKClient | None = None
        self._run: AgentRun | None = None

    def _build_options(self, run: AgentRun) -> ClaudeAgentOptions:
        """Build ClaudeAgentOptions for this run."""
        server = create_agentml_server(self.lab)
        return ClaudeAgentOptions(
            mcp_servers={"agentml": server},
            allowed_tools=[*AGENTML_TOOLS, *BUILTIN_TOOLS],
            system_prompt=build_system_prompt(run),
            permission_mode="acceptEdits",
            max_turns=self.max_turns,
            max_budget_usd=self.max_budget_usd,
            cwd=self.cwd,
        )

    async def start(self, prompt: str, task_id: str | None = None) -> AgentRun:
        """Start an agent run. Returns the AgentRun (events stream in background)."""
        run = AgentRun(
            task_id=task_id or generate_id(),
            prompt=prompt,
            status=RunStatus.RUNNING,
            started_at=datetime.now(UTC),
        )
        self._run = run

        options = self._build_options(run)
        self._client = ClaudeSDKClient(options=options)

        return run

    async def execute(self, run: AgentRun) -> None:
        """Execute the agent run (blocking). Call in a background task."""
        try:
            async with self._client as client:
                await client.query(run.prompt)

                async for message in client.receive_response():
                    event = self._message_to_event(message)
                    if event:
                        run.events.append(event)

                    if isinstance(message, ResultMessage):
                        run.session_id = message.session_id
                        run.total_cost_usd = message.total_cost_usd
                        run.num_turns = message.num_turns
                        run.status = (
                            RunStatus.FAILED if message.is_error else RunStatus.COMPLETED
                        )

            run.completed_at = datetime.now(UTC)

        except Exception as e:
            run.status = RunStatus.FAILED
            run.error = str(e)
            run.completed_at = datetime.now(UTC)
            logger.error("agent_run_failed", run_id=run.id, error=str(e))

    async def stop(self) -> None:
        """Interrupt the running agent."""
        if self._client:
            await self._client.interrupt()
            if self._run:
                self._run.status = RunStatus.STOPPED
                self._run.completed_at = datetime.now(UTC)

    def _message_to_event(self, message: Any) -> AgentEvent | None:
        """Convert a Claude SDK message to an AgentEvent."""
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, ToolUseBlock):
                    return AgentEvent(
                        event_type="tool_call",
                        data={"tool": block.name, "input": block.input},
                    )
                if isinstance(block, ToolResultBlock):
                    return AgentEvent(
                        event_type="tool_result",
                        data={"tool_use_id": block.tool_use_id, "content": block.content},
                    )
                if isinstance(block, TextBlock):
                    return AgentEvent(
                        event_type="text",
                        data={"text": block.text},
                    )
        if isinstance(message, ResultMessage):
            return AgentEvent(
                event_type="result",
                data={
                    "session_id": message.session_id,
                    "turns": message.num_turns,
                    "cost_usd": message.total_cost_usd,
                    "duration_ms": message.duration_ms,
                    "is_error": message.is_error,
                },
            )
        return None
```

---

## 3. System Prompt Design

**File:** `src/agentml/agents/prompts.py`

```python
"""System prompt templates for AgentML agent sessions."""

from agentml.agents.orchestrator import AgentRun


def build_system_prompt(run: AgentRun) -> str:
    """Build the system prompt for a Claude Code agent session."""
    hints_section = ""
    # Tool hints would be injected here (see section 8)

    return f"""You are an autonomous ML research agent operating within AgentML.

## Your role
You systematically explore ML approaches to solve a given problem. You create
experiments, write and execute code, track results, and record learnings.

## Your task ID
{run.task_id}

Always pass this task_id when calling create_experiment so experiments are linked
to this task.

## Available AgentML tools (via MCP)
These tools manage experiments and knowledge in AgentML's platform:

- **create_experiment** — Register a new experiment with a hypothesis BEFORE running code
- **complete_experiment** — Mark as done with metrics after code runs successfully
- **fail_experiment** — Mark as failed if code errors out
- **get_experiment** / **list_experiments** — Review experiment state
- **compare_experiments** — Side-by-side metric comparison across experiments
- **log_metrics** / **log_params** — Log to the tracking backend (MLflow/file)
- **write_knowledge** — Record a learning or insight (always do this!)
- **search_knowledge** — Check if you already know something relevant
- **list_knowledge** — Review all recorded knowledge

## Code execution
You also have Bash, Read, Write, and Edit tools from Claude Code.
Use Bash to run Python scripts for training, evaluation, etc.

## Workflow
1. **Search knowledge** first — have we learned anything about this problem before?
2. **Plan** your experimental approach (models, features, hyperparameters)
3. For each experiment:
   a. Call `create_experiment` with a clear hypothesis
   b. Write and run code with Bash (install packages as needed)
   c. Parse the metrics from stdout
   d. Call `log_metrics` then `complete_experiment` (or `fail_experiment`)
   e. Call `write_knowledge` with what you learned
4. After 2+ experiments, call `compare_experiments` to assess progress
5. Iterate: try new approaches informed by what you've learned
6. Summarize your findings when you're done

## Important rules
- Always create_experiment BEFORE running code for it
- Always complete_experiment or fail_experiment AFTER — never leave experiments in running state
- Log metrics to the tracking backend for every experiment
- Write knowledge atoms when you discover something meaningful
- Be systematic: change one thing at a time between experiments
- Include print statements in your code to output metrics as JSON
{hints_section}"""
```

---

## 4. API Routes

**File:** `src/agentml/api/routers/agent.py`

```python
"""Agent router — start, monitor, and stop agent research sessions."""

import asyncio
from datetime import UTC, datetime

from fastapi import APIRouter, Request
from pydantic import BaseModel

from agentml.agents.orchestrator import AgentOrchestrator, AgentRun, RunStatus
from agentml.runtime.lab import LabEnvironment

router = APIRouter(prefix="/agent", tags=["agent"])

# In-memory store of active and completed runs
_runs: dict[str, AgentRun] = {}
_orchestrators: dict[str, AgentOrchestrator] = {}


def _get_lab(request: Request) -> LabEnvironment:
    return request.app.state.lab


# --- Request/Response models ---

class ToolHintRequest(BaseModel):
    name: str
    description: str
    source: str
    code_template: str = ""

class StartRunRequest(BaseModel):
    prompt: str
    tool_hints: list[ToolHintRequest] = []
    max_turns: int = 50
    max_budget_usd: float | None = None

class AgentEventResponse(BaseModel):
    id: str
    timestamp: str
    event_type: str
    data: dict

class AgentRunResponse(BaseModel):
    id: str
    task_id: str
    prompt: str
    status: str
    events: list[AgentEventResponse] = []
    started_at: str | None = None
    completed_at: str | None = None
    total_cost_usd: float | None = None
    num_turns: int = 0
    error: str | None = None


# --- Routes ---

@router.post("/run", response_model=AgentRunResponse)
async def start_run(body: StartRunRequest, request: Request) -> AgentRunResponse:
    """Start an agent research session."""
    lab = _get_lab(request)
    settings = request.app.state.settings

    orchestrator = AgentOrchestrator(
        lab,
        max_turns=body.max_turns,
        max_budget_usd=body.max_budget_usd,
    )

    run = await orchestrator.start(prompt=body.prompt)

    _runs[run.id] = run
    _orchestrators[run.id] = orchestrator

    # Execute in background
    asyncio.create_task(_run_agent(run, orchestrator))

    return _to_response(run)


@router.get("/runs", response_model=list[AgentRunResponse])
async def list_runs() -> list[AgentRunResponse]:
    """List all agent runs."""
    return [_to_response(r) for r in _runs.values()]


@router.get("/runs/{run_id}", response_model=AgentRunResponse)
async def get_run(run_id: str) -> AgentRunResponse:
    """Get agent run status and events."""
    run = _runs.get(run_id)
    if not run:
        from fastapi import HTTPException
        raise HTTPException(404, f"Run {run_id} not found")
    return _to_response(run)


@router.post("/runs/{run_id}/stop")
async def stop_run(run_id: str) -> dict:
    """Stop a running agent."""
    orchestrator = _orchestrators.get(run_id)
    if not orchestrator:
        from fastapi import HTTPException
        raise HTTPException(404, f"Run {run_id} not found")
    await orchestrator.stop()
    return {"status": "stopped"}


# --- SSE endpoint (requires sse-starlette) ---

@router.get("/runs/{run_id}/events")
async def stream_events(run_id: str, request: Request):
    """Server-Sent Events stream for an agent run."""
    from sse_starlette.sse import EventSourceResponse

    run = _runs.get(run_id)
    if not run:
        from fastapi import HTTPException
        raise HTTPException(404, f"Run {run_id} not found")

    async def event_generator():
        seen = 0
        while True:
            # Yield new events
            while seen < len(run.events):
                event = run.events[seen]
                seen += 1
                yield {
                    "event": event.event_type,
                    "data": json.dumps({
                        "id": event.id,
                        "timestamp": event.timestamp.isoformat(),
                        "event_type": event.event_type,
                        "data": event.data,
                    }, default=str),
                }

            # Check if run is done
            if run.status in (RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.STOPPED):
                yield {"event": "done", "data": json.dumps({"status": run.status.value})}
                return

            await asyncio.sleep(0.3)

    return EventSourceResponse(event_generator())


# --- Helpers ---

async def _run_agent(run: AgentRun, orchestrator: AgentOrchestrator) -> None:
    """Background task that executes the agent."""
    await orchestrator.execute(run)


def _to_response(run: AgentRun) -> AgentRunResponse:
    return AgentRunResponse(
        id=run.id,
        task_id=run.task_id,
        prompt=run.prompt,
        status=run.status.value,
        events=[
            AgentEventResponse(
                id=e.id,
                timestamp=e.timestamp.isoformat(),
                event_type=e.event_type,
                data=e.data,
            )
            for e in run.events[-50:]  # Last 50 events only
        ],
        started_at=run.started_at.isoformat() if run.started_at else None,
        completed_at=run.completed_at.isoformat() if run.completed_at else None,
        total_cost_usd=run.total_cost_usd,
        num_turns=run.num_turns,
        error=run.error,
    )
```

**Wire into app:**

```python
# src/agentml/api/app.py — add:
from agentml.api.routers import agent
app.include_router(agent.router)
```

---

## 5. Event Streaming

### How events flow

```
ClaudeSDKClient.receive_response()
    │
    ├── AssistantMessage(ToolUseBlock)  →  AgentEvent("tool_call", {tool, input})
    ├── AssistantMessage(ToolResultBlock) →  AgentEvent("tool_result", {output})
    ├── AssistantMessage(TextBlock)     →  AgentEvent("text", {text})
    └── ResultMessage                   →  AgentEvent("result", {cost, turns, ...})
    │
    ▼  Appended to run.events[]
    │
    ▼  SSE endpoint polls run.events[]
    │
    ▼  Frontend EventSource receives events
```

### Optional: Hooks for richer events

Using Claude Agent SDK hooks, we can capture events before/after every tool call with richer context:

```python
from claude_agent_sdk import HookMatcher, HookContext

async def pre_tool_hook(
    input_data: dict, tool_use_id: str | None, context: HookContext
) -> dict:
    """Capture tool call events for the UI."""
    run.events.append(AgentEvent(
        event_type="tool_starting",
        data={
            "tool": input_data.get("tool_name"),
            "input": input_data.get("tool_input"),
        },
    ))
    return {}  # Don't modify the tool call

async def post_tool_hook(
    input_data: dict, tool_use_id: str | None, context: HookContext
) -> dict:
    """Capture tool results for the UI."""
    run.events.append(AgentEvent(
        event_type="tool_completed",
        data={
            "tool": input_data.get("tool_name"),
            "response": str(input_data.get("tool_response", ""))[:500],
        },
    ))
    return {}

# Add to ClaudeAgentOptions:
hooks={
    "PreToolUse": [HookMatcher(hooks=[pre_tool_hook])],
    "PostToolUse": [HookMatcher(hooks=[post_tool_hook])],
}
```

---

## 6. Frontend Changes

### 6.1 New types

**File:** `frontend/src/types.ts` — add:

```typescript
export interface AgentRun {
  id: string;
  task_id: string;
  prompt: string;
  status: "pending" | "running" | "completed" | "failed" | "stopped";
  events: AgentEvent[];
  started_at: string | null;
  completed_at: string | null;
  total_cost_usd: number | null;
  num_turns: number;
  error: string | null;
}

export interface AgentEvent {
  id: string;
  timestamp: string;
  event_type: string;
  data: Record<string, unknown>;
}

export interface ToolHint {
  name: string;
  description: string;
  source: string;
  code_template?: string;
}
```

### 6.2 New hooks

**File:** `frontend/src/hooks/use-agent.ts`

```typescript
import useSWR from "swr";
import { apiFetch } from "@/lib/api";
import type { AgentRun } from "@/types";

// List all runs
export function useAgentRuns() {
  return useSWR<AgentRun[]>("/agent/runs", (url: string) => apiFetch<AgentRun[]>(url));
}

// Get single run (poll while running)
export function useAgentRun(id: string | undefined) {
  return useSWR<AgentRun>(
    id ? `/agent/runs/${id}` : null,
    (url: string) => apiFetch<AgentRun>(url),
    { refreshInterval: (data) => data?.status === "running" ? 1000 : 0 },
  );
}

// Start a run
export async function startAgentRun(prompt: string, toolHints?: ToolHint[]): Promise<AgentRun> {
  return apiFetch<AgentRun>("/agent/run", {
    method: "POST",
    body: JSON.stringify({ prompt, tool_hints: toolHints }),
  });
}

// Stop a run
export async function stopAgentRun(runId: string): Promise<void> {
  await apiFetch(`/agent/runs/${runId}/stop`, { method: "POST" });
}
```

**File:** `frontend/src/hooks/use-agent-events.ts`

```typescript
import { useState, useEffect, useRef } from "react";
import type { AgentEvent } from "@/types";

const API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";

export function useAgentEvents(runId: string | undefined) {
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [done, setDone] = useState(false);
  const esRef = useRef<EventSource | null>(null);

  useEffect(() => {
    if (!runId) return;

    const es = new EventSource(`${API_BASE}/agent/runs/${runId}/events`);
    esRef.current = es;

    es.addEventListener("tool_call", (e) => {
      setEvents((prev) => [...prev, JSON.parse(e.data)]);
    });
    es.addEventListener("tool_result", (e) => {
      setEvents((prev) => [...prev, JSON.parse(e.data)]);
    });
    es.addEventListener("text", (e) => {
      setEvents((prev) => [...prev, JSON.parse(e.data)]);
    });
    es.addEventListener("done", () => {
      setDone(true);
      es.close();
    });
    es.onerror = () => {
      setDone(true);
      es.close();
    };

    return () => es.close();
  }, [runId]);

  return { events, done };
}
```

### 6.3 Agent page

**File:** `frontend/src/pages/agent.tsx`

Key components:

| Component | Purpose |
|---|---|
| `AgentPromptForm` | Prompt textarea + tool hint cards (add/remove) + "Start Research" button |
| `AgentRunView` | Active run view: status badge, event feed, experiment cards, stop button |
| `EventFeed` | Scrolling list of agent events, color-coded by type |
| `RunSummary` | Final summary: cost, turns, duration, best experiment |

Layout:

```
┌─────────────────────────────────────────────┐
│  Agent Research                              │
├─────────────────────────────────────────────┤
│  ┌─────────────────────────────────────────┐│
│  │ Prompt textarea                          ││
│  │ "Improve accuracy of Boston housing..."  ││
│  └─────────────────────────────────────────┘│
│  Tool Hints:                                 │
│  ┌──────────┐ ┌──────────┐ [+ Add Hint]     │
│  │fetch_data│ │eval_rmse │                   │
│  └──────────┘ └──────────┘                   │
│                                              │
│  [Start Research]                            │
├─────────────────────────────────────────────┤
│  Agent: ● Running  (turn 7/50)  $0.12       │
│  ┌──────────────────────────────────────────┤
│  │ Event Feed            │ Experiments       │
│  │ ▶ create_experiment   │ ┌──────────────┐ │
│  │ ▶ Bash: python train  │ │ Exp 1: 0.72  │ │
│  │ ▶ log_metrics         │ │ Exp 2: 0.87  │ │
│  │ ▶ write_knowledge     │ └──────────────┘ │
│  │ ▶ create_experiment   │                   │
│  │ ▶ Bash: python train  │ Knowledge        │
│  │ ...                   │ • LR baseline R²  │
│  │                       │ • RF improves...  │
│  └──────────────────────────────────────────┤
│  [Stop Agent]                                │
└──────────────────────────────────────────────┘
```

### 6.4 Route addition

```tsx
// App.tsx — add:
import AgentPage from "@/pages/agent";

<Route path="agent" element={<AgentPage />} />
```

### 6.5 Nav item

Add "Agent" link in `frontend/src/components/layout/shell.tsx` nav.

---

## 7. Configuration

### Settings additions

**File:** `src/agentml/config/settings.py`

```python
class AgentSettings(BaseSettings):
    """Agent execution configuration."""
    max_turns: int = 50                  # Max tool-use round trips
    max_budget_usd: float | None = None  # Max spend per run (None = unlimited)
    permission_mode: str = "acceptEdits" # Claude Code permission mode
    cwd: str | None = None               # Working directory for code execution

class Settings(BaseSettings):
    ...
    agent: AgentSettings = Field(default_factory=AgentSettings)
```

### Environment variables

```bash
AGENTML__AGENT__MAX_TURNS=100
AGENTML__AGENT__MAX_BUDGET_USD=5.00
```

---

## 8. Task-Level Tool Hints

Tool hints let users tell the agent about data sources or domain-specific tools it should create.

### How they work

1. User submits hints via the UI (name, description, source URL)
2. Hints are injected into the system prompt as instructions
3. Claude Code uses `WebFetch` to read the source, then `Bash` to write/test a loader
4. The agent naturally creates reusable code — no dynamic MCP tool creation needed

This is the key simplification: **Claude Code can already read URLs and write code.** We don't need a `create_tool` meta-tool. We just need to tell the agent about the data sources in the prompt.

### System prompt injection

```python
# In build_system_prompt():
if run.tool_hints:
    hints = "\n## Data sources & hints\n"
    hints += "The user has provided the following information:\n\n"
    for h in run.tool_hints:
        hints += f"- **{h.name}**: {h.description}\n"
        hints += f"  Source: {h.source}\n"
        if h.code_template:
            hints += f"  Starter code:\n```python\n{h.code_template}\n```\n"
    hints += "\nUse WebFetch to read these sources if needed, then write appropriate data loading code.\n"
```

---

## 9. File-by-File Change Map

### New files

| File | Purpose |
|---|---|
| `src/agentml/agents/orchestrator.py` | `AgentOrchestrator`, `AgentRun`, `AgentEvent` |
| `src/agentml/agents/prompts.py` | System prompt template |
| `src/agentml/api/routers/agent.py` | Agent run API routes + SSE |
| `frontend/src/pages/agent.tsx` | Agent page |
| `frontend/src/hooks/use-agent.ts` | Agent runs hooks |
| `frontend/src/hooks/use-agent-events.ts` | SSE event stream hook |
| `frontend/src/components/agent/agent-prompt-form.tsx` | Prompt + tool hints form |
| `frontend/src/components/agent/agent-run-view.tsx` | Live agent run view |
| `frontend/src/components/agent/event-feed.tsx` | Event feed component |
| `frontend/src/components/agent/run-summary.tsx` | Run summary component |
| `tests/unit/test_orchestrator.py` | Orchestrator tests (mocked SDK) |
| `tests/e2e/test_agent_run.py` | E2E agent run test |

### Modified files

| File | Change |
|---|---|
| `src/agentml/api/app.py` | Include agent router |
| `src/agentml/config/settings.py` | Add `AgentSettings` |
| `pyproject.toml` | Add `sse-starlette` dependency |
| `frontend/src/types.ts` | Add `AgentRun`, `AgentEvent`, `ToolHint` types |
| `frontend/src/App.tsx` | Add agent route |
| `frontend/src/components/layout/shell.tsx` | Add agent nav item |

---

## 10. Implementation Steps

```
Step 1 — Dependencies                         ~15 min
├── Add sse-starlette to pyproject.toml
└── npm install (if any new frontend deps)

Step 2 — Agent orchestrator                    ~2 hours
├── Create agents/orchestrator.py
│   ├── AgentRun & AgentEvent dataclasses
│   ├── AgentOrchestrator class
│   └── Message → Event conversion
├── Create agents/prompts.py
│   └── build_system_prompt()
└── Unit tests (mocked ClaudeSDKClient)

Step 3 — API routes                            ~1.5 hours
├── Create api/routers/agent.py
│   ├── POST /agent/run
│   ├── GET /agent/runs, /agent/runs/{id}
│   ├── POST /agent/runs/{id}/stop
│   └── GET /agent/runs/{id}/events (SSE)
├── Wire into app.py
└── E2E test

Step 4 — Configuration                        ~30 min
├── Add AgentSettings to settings.py
└── Wire into orchestrator

Step 5 — Frontend: types & hooks              ~1 hour
├── Add types to types.ts
├── Create use-agent.ts
└── Create use-agent-events.ts

Step 6 — Frontend: agent page                 ~2-3 hours
├── Create agent-prompt-form.tsx
├── Create agent-run-view.tsx
├── Create event-feed.tsx
├── Create run-summary.tsx
├── Create pages/agent.tsx
├── Add route to App.tsx
└── Add nav item to shell.tsx

Step 7 — Integration test                      ~1 hour
├── Start backend + frontend
├── Submit a prompt via UI
├── Verify: events stream, experiments appear, knowledge saved
└── Test stop button

Step 8 — Polish                                ~1 hour
├── Error handling edge cases
├── Loading states
└── Cleanup
```

**Total estimated time: ~8-10 hours**

---

## 11. End-to-End Example: Boston Housing

### User submits via UI

**Prompt:**
> Improve the accuracy of the Boston housing prediction problem. Start with a linear regression baseline, then try more advanced models. Target: R² > 0.85.

**Tool hints:**
| Name | Description | Source |
|---|---|---|
| `fetch_dataset` | Load the Boston housing dataset | `https://scikit-learn.org/1.0/modules/generated/sklearn.datasets.load_boston.html` |

### What appears in the UI

```
● Agent Running — Turn 1

▶ search_knowledge("boston housing")        → No prior knowledge
▶ text: "I'll start by exploring the data..."
▶ create_experiment(hypothesis="Linear regression baseline")  → exp_01ABC
▶ Bash: pip install scikit-learn numpy      → OK
▶ Bash: python train_baseline.py           → {"r2": 0.72, "rmse": 4.87}
▶ log_metrics(exp_01ABC, {r2: 0.72, rmse: 4.87})
▶ complete_experiment(exp_01ABC, metrics...)
▶ write_knowledge("Linear regression baseline achieves R²=0.72")

● Agent Running — Turn 8

▶ create_experiment(hypothesis="Random Forest with default params")  → exp_02DEF
▶ Bash: python train_rf.py                → {"r2": 0.87, "rmse": 3.45}
▶ log_metrics(exp_02DEF, {r2: 0.87, rmse: 3.45})
▶ complete_experiment(exp_02DEF)
▶ write_knowledge("Random Forest significantly outperforms LR, R²=0.87")
▶ compare_experiments([exp_01ABC, exp_02DEF])

● Agent Running — Turn 15

▶ create_experiment(hypothesis="Gradient Boosting with tuned params")  → exp_03GHI
▶ Bash: python train_gb.py                → {"r2": 0.91, "rmse": 2.89}
▶ ...

● Agent Completed — 22 turns, $0.34, 4m 12s

Summary: Best model is Gradient Boosting (R²=0.91). Key findings:
- Feature engineering on LSTAT and RM improves all models
- Random Forest and GB both exceed R²=0.85 target
- Linear regression is a solid baseline at R²=0.72

Experiments: 5 created, 4 completed, 1 failed
Knowledge atoms: 7 recorded
```

### What persists in AgentML

- **Experiments** in `experiment_store` — full lifecycle with metrics
- **Knowledge atoms** in `memory_store` — learnings for future tasks
- **Metrics** in `tracking` (MLflow or file) — full metric history
- **Code** on disk in the agent's working directory — all scripts the agent wrote

---

## Appendix: What We Removed vs. Original Plan

The original `end-to-end-agent-harness.md` included complexity that the Claude Agent SDK makes unnecessary:

| Original concept | SDK replacement | Simplification |
|---|---|---|
| Custom `ToolRegistry` class | `@tool` + `create_sdk_mcp_server()` | No custom tool registry code |
| JSON Schema generation from type hints | SDK's `input_schema` parameter | Schema defined inline |
| Custom agent loop (plan→act→observe) | `ClaudeSDKClient` handles this | No agent loop code at all |
| `execute_code` / `install_packages` tools | Claude Code's built-in `Bash` tool | No sandbox tools needed |
| `create_tool` dynamic meta-tool | Agent uses `Bash` + `Write` to create code | Prompt hints instead |
| Custom `Sandbox` enhancements | Claude Code sandbox + `Bash` | Keep existing sandbox for non-agent use |
| Manual message parsing for tool calls | SDK yields typed `ToolUseBlock` etc. | Type-safe message handling |
| `Agent` field in `LabEnvironment` | Orchestrator creates client per-run | No LabEnvironment changes |
| `ToolRuntime` wiring in `build_lab()` | MCP server created per-run by orchestrator | No DI changes |

**Net result:** ~60% less code to write, and the complex parts (agent loop, tool dispatch, code execution) are handled by a production-tested SDK.
