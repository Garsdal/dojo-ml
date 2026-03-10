# End-to-End Agent Harness v2 — Agent Sessions, API & UI

> **Prerequisite:** v1 is complete — AgentML MCP tools exist as `ToolDef` instances with the `ClaudeToolAdapter`.
>
> **Goal:** Wire an agent into the FastAPI backend so users can start, monitor, and stop ML research sessions from the UI. The agent backend is abstracted behind an `AgentBackend` interface — swappable between Claude, Copilot, or any future SDK.

---

## Key Design Principles

1. **Claude Code does the heavy lifting** — we are a thin orchestration layer
2. **The agent backend is a port** — `AgentBackend` ABC defines what an agent can do; `ClaudeAgentBackend` is the first adapter
3. **Mirrors v1's tool adapter pattern** — tools have `ToolDef` → `ToolAdapter`; agent sessions have `AgentBackend` → `ClaudeAgentBackend`

From the Claude Agent SDK docs, the Claude implementation uses:

| SDK Feature | What it gives us | Our usage |
|---|---|---|
| `ClaudeSDKClient` | Persistent session, multi-turn, interrupt | One client per agent run |
| `ClaudeAgentOptions` | System prompt, permissions, budget, hooks | Full agent configuration |
| Hooks (`PreToolUse`, `PostToolUse`) | Intercept every tool call | Event streaming to UI |
| `ResultMessage` | Cost, duration, turns, session_id | Run summary & cost tracking |
| `AssistantMessage` / `ToolUseBlock` | Real-time message stream | Event feed in UI |
| `max_turns` / `max_budget_usd` | Safety limits | Prevent runaway agents |
| `client.interrupt()` | Stop the agent mid-task | Stop button in UI |
| Built-in tools (`Bash`, `Write`, etc.) | Code execution, file I/O | Agent writes & runs ML code |

```
UI → POST /agent/run → AgentOrchestrator
                            │
                            ├── Build LabEnvironment (existing)
                            ├── Collect AgentML ToolDefs (v1)
                            ├── Select AgentBackend (from config)
                            │     ├── ClaudeAgentBackend (claude-agent-sdk)
                            │     └── (future) CopilotAgentBackend, etc.
                            ├── backend.start(run) → launch session
                            ├── backend.execute(run) → stream events
                            ├── Stream events via SSE
                            └── backend.stop() → interrupt
```

---

## Table of Contents

1. [Architecture](#1-architecture)
2. [Agent Backend Abstraction](#2-agent-backend-abstraction)
3. [Claude Agent Backend](#3-claude-agent-backend)
4. [Agent Orchestrator](#4-agent-orchestrator)
5. [System Prompt Design](#5-system-prompt-design)
6. [API Routes](#6-api-routes)
7. [Event Streaming](#7-event-streaming)
8. [Frontend Changes](#8-frontend-changes)
9. [Configuration](#9-configuration)
10. [Task-Level Tool Hints](#10-task-level-tool-hints)
11. [File-by-File Change Map](#11-file-by-file-change-map)
12. [Implementation Steps](#12-implementation-steps)
13. [End-to-End Example: Boston Housing](#13-end-to-end-example-boston-housing)

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
│  AgentOrchestrator (per run) — SDK-agnostic                   │
│  ├── AgentBackend (interface / port)                         │
│  │   ├── ClaudeAgentBackend (claude-agent-sdk)               │
│  │   │   ├── Uses ClaudeToolAdapter to adapt ToolDefs        │
│  │   │   ├── ClaudeSDKClient for session management          │
│  │   │   └── Claude-specific message → AgentEvent mapping    │
│  │   └── (future) CopilotAgentBackend, etc.                  │
│  ├── ToolDefs from v1 (framework-agnostic)                   │
│  ├── System prompt builder                                    │
│  └── Event buffer → SSE endpoints                             │
│                                                               │
│  LabEnvironment (unchanged)                                   │
│  ├── experiment_store                                         │
│  ├── memory_store                                             │
│  ├── tracking                                                 │
│  └── artifact_store                                           │
└───────────────────────────────────────────────────────────────┘
```

### Layering: v1 Tools + v2 Agent Backend

```
                         ┌─────────────────────┐
                         │  AgentOrchestrator   │  SDK-agnostic
                         │  (lifecycle, events) │
                         └──────────┬──────────┘
                                    │ uses
              ┌─────────────────────┼─────────────────────┐
              │                     │                     │
     ┌────────▼────────┐  ┌────────▼────────┐   ┌────────▼────────┐
     │  AgentBackend    │  │  ToolDef[]      │   │  System Prompt  │
     │  (ABC / port)    │  │  (from v1)      │   │  (from prompts) │
     └────────┬─────────┘  └────────┬────────┘   └─────────────────┘
              │                     │
   ┌──────────▼──────────┐  ┌──────▼──────────┐
   │ ClaudeAgentBackend  │  │ ClaudeToolAdapter│   (Both in adapters/)
   │ (ClaudeSDKClient)   │  │ (@tool + MCP)   │
   └─────────────────────┘  └─────────────────┘
```

---

## 2. Agent Backend Abstraction

The `AgentBackend` ABC defines the interface for launching, executing, and stopping an agent session. It knows nothing about Claude, Copilot, or any specific SDK.

### 2.1 Domain Types (shared, SDK-agnostic)

**File:** `src/agentml/agents/types.py`

```python
"""Shared types for agent sessions — SDK-agnostic."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from agentml.utils.ids import generate_id


class RunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    STOPPED = "stopped"


@dataclass
class AgentEvent:
    """A single event in the agent run timeline.

    All backends emit events in this common format. The orchestrator and
    SSE layer only deal with AgentEvent — never SDK-specific message types.
    """

    id: str = field(default_factory=generate_id)
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    event_type: str = ""  # tool_call, tool_result, text, error, status_change, result
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentRunConfig:
    """Configuration for a single agent run — passed to AgentBackend.start().

    Framework-agnostic. Each backend interprets these fields in its own way.
    """

    system_prompt: str = ""
    max_turns: int = 50
    max_budget_usd: float | None = None
    permission_mode: str = "acceptEdits"
    cwd: str | None = None


@dataclass
class AgentRunResult:
    """Summary returned by AgentBackend.execute() when the run completes.

    Backends populate whichever fields they support. Fields that don't apply
    to a given backend are left as None / 0.
    """

    session_id: str | None = None
    total_cost_usd: float | None = None
    num_turns: int = 0
    duration_ms: int | None = None
    is_error: bool = False
    error_message: str | None = None


@dataclass
class AgentRun:
    """Full state of a single agent run — managed by the orchestrator."""

    id: str = field(default_factory=generate_id)
    task_id: str = ""
    prompt: str = ""
    status: RunStatus = RunStatus.PENDING
    events: list[AgentEvent] = field(default_factory=list)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    config: AgentRunConfig = field(default_factory=AgentRunConfig)
    result: AgentRunResult | None = None
    error: str | None = None
```

### 2.2 AgentBackend ABC

**File:** `src/agentml/agents/backend.py`

```python
"""Agent backend interface — the port for agent session execution."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

from agentml.agents.types import AgentEvent, AgentRunConfig, AgentRunResult
from agentml.tools.base import ToolDef


class AgentBackend(ABC):
    """Abstract interface for running an agent session.

    Each concrete backend (Claude, Copilot, etc.) implements this interface.
    The AgentOrchestrator delegates all SDK-specific logic here.

    Lifecycle:
        1. configure() — set up the backend with tools, prompt, and config
        2. execute()   — run the agent; yields AgentEvents as they happen
        3. stop()      — interrupt a running session (if supported)
    """

    @abstractmethod
    async def configure(
        self,
        tool_defs: list[ToolDef],
        config: AgentRunConfig,
    ) -> None:
        """Configure the backend for a run.

        This is called once before execute(). The backend should:
        - Adapt tool_defs to its SDK format (using the appropriate ToolAdapter)
        - Build any SDK-specific client/session configuration
        - Prepare to accept a prompt via execute()

        Args:
            tool_defs: Framework-agnostic tool definitions from v1.
            config: Run configuration (system prompt, limits, etc.).
        """
        ...

    @abstractmethod
    async def execute(self, prompt: str) -> AsyncIterator[AgentEvent]:
        """Execute the agent with the given prompt.

        Yields AgentEvent instances as the agent works. The orchestrator
        appends these to AgentRun.events and streams them via SSE.

        When the agent finishes (or errors), should yield a final event
        with event_type="result" containing the AgentRunResult as data.

        Args:
            prompt: The user's research prompt.

        Yields:
            AgentEvent instances (tool_call, tool_result, text, result, etc.)
        """
        ...

    @abstractmethod
    async def stop(self) -> None:
        """Interrupt a running agent session.

        Should be safe to call even if the agent has already stopped.
        """
        ...

    @property
    def name(self) -> str:
        """Human-readable backend name (e.g. 'claude', 'copilot')."""
        return self.__class__.__name__
```

### 2.3 Why This Design

| Concern | How it's handled |
|---|---|
| **SDK independence** | `AgentOrchestrator` only sees `AgentBackend` — never imports `claude_agent_sdk` |
| **Testability** | Tests can use a `StubAgentBackend` that yields canned events — no real SDK needed |
| **Swappability** | Config sets `agent.backend = "copilot"` → different backend, same orchestrator |
| **Event normalization** | All backends emit `AgentEvent` — SSE layer and frontend don't care which SDK ran |
| **Tool reuse** | Backends receive `list[ToolDef]` from v1 — each adapts tools using its own `ToolAdapter` |

### 2.4 Relationship to Existing `Agent` Interface

The existing `src/agentml/interfaces/agent.py` defines an `Agent` ABC with `run(task, lab)`. This was designed for the `StubAgent` pattern (synchronous task execution). 

`AgentBackend` is a **different abstraction** — it manages an interactive, streaming session with an external AI agent. The two could eventually be unified, but for v2 we keep them separate:

- `Agent` → "run a task and return results" (batch, internal)
- `AgentBackend` → "launch a streaming AI session with tools" (interactive, external)

---

## 3. Claude Agent Backend

**File:** `src/agentml/agents/backends/claude.py`

This is the first (and for now only) concrete implementation of `AgentBackend`.

```python
"""Claude Agent SDK backend — runs agent sessions via ClaudeSDKClient."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    HookContext,
    HookMatcher,
    ResultMessage,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
)

from agentml.agents.backend import AgentBackend
from agentml.agents.types import AgentEvent, AgentRunConfig, AgentRunResult
from agentml.tools.adapters.claude import ClaudeToolAdapter
from agentml.tools.base import ToolDef
from agentml.utils.logging import get_logger

logger = get_logger(__name__)

# Claude Code built-in tools the agent may use
BUILTIN_TOOLS = ["Bash", "Read", "Write", "Edit", "WebFetch"]


class ClaudeAgentBackend(AgentBackend):
    """Runs an agent session using the Claude Agent SDK.

    Uses ClaudeToolAdapter from v1 to convert ToolDefs → Claude MCP tools.
    Uses ClaudeSDKClient for session management, streaming, and interruption.
    """

    def __init__(self) -> None:
        self._client: ClaudeSDKClient | None = None
        self._options: ClaudeAgentOptions | None = None
        self._tool_adapter = ClaudeToolAdapter()
        self._tool_defs: list[ToolDef] = []

    async def configure(
        self,
        tool_defs: list[ToolDef],
        config: AgentRunConfig,
    ) -> None:
        """Configure the Claude agent session.

        Converts ToolDefs to Claude format via ClaudeToolAdapter,
        builds ClaudeAgentOptions with the system prompt and limits.
        """
        self._tool_defs = tool_defs

        # Use the v1 ClaudeToolAdapter to create the MCP server
        server = self._tool_adapter.create_server("agentml", tool_defs)
        allowed_agentml = self._tool_adapter.tool_names_prefixed("agentml", tool_defs)

        self._options = ClaudeAgentOptions(
            mcp_servers={"agentml": server},
            allowed_tools=[*allowed_agentml, *BUILTIN_TOOLS],
            system_prompt=config.system_prompt,
            permission_mode=config.permission_mode,
            max_turns=config.max_turns,
            max_budget_usd=config.max_budget_usd,
            cwd=config.cwd,
        )

        self._client = ClaudeSDKClient(options=self._options)

    async def execute(self, prompt: str) -> AsyncIterator[AgentEvent]:
        """Execute the agent run, yielding events as they arrive."""
        if not self._client:
            msg = "Backend not configured — call configure() first"
            raise RuntimeError(msg)

        try:
            async with self._client as client:
                await client.query(prompt)

                async for message in client.receive_response():
                    events = self._message_to_events(message)
                    for event in events:
                        yield event

                    # If this is the result message, yield the summary event
                    if isinstance(message, ResultMessage):
                        yield AgentEvent(
                            event_type="result",
                            data={
                                "session_id": message.session_id,
                                "turns": message.num_turns,
                                "cost_usd": message.total_cost_usd,
                                "duration_ms": message.duration_ms,
                                "is_error": message.is_error,
                            },
                        )

        except Exception as e:
            logger.error("claude_backend_error", error=str(e))
            yield AgentEvent(
                event_type="error",
                data={"error": str(e)},
            )

    async def stop(self) -> None:
        """Interrupt the Claude agent session."""
        if self._client:
            await self._client.interrupt()

    @property
    def name(self) -> str:
        return "claude"

    # --- Private helpers ---

    def _message_to_events(self, message: Any) -> list[AgentEvent]:
        """Convert a Claude SDK message to AgentEvent(s).

        A single AssistantMessage may contain multiple content blocks,
        so we return a list.
        """
        events: list[AgentEvent] = []

        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, ToolUseBlock):
                    events.append(AgentEvent(
                        event_type="tool_call",
                        data={"tool": block.name, "input": block.input},
                    ))
                elif isinstance(block, ToolResultBlock):
                    events.append(AgentEvent(
                        event_type="tool_result",
                        data={
                            "tool_use_id": block.tool_use_id,
                            "content": block.content,
                        },
                    ))
                elif isinstance(block, TextBlock):
                    events.append(AgentEvent(
                        event_type="text",
                        data={"text": block.text},
                    ))

        return events
```

### 3.1 Optional: Hooks for Richer Events

Using Claude Agent SDK hooks, we can capture events before/after every tool call:

```python
# Inside ClaudeAgentBackend.configure(), add hooks to options:

async def pre_tool_hook(
    input_data: dict, tool_use_id: str | None, context: HookContext
) -> dict:
    """Capture pre-tool events for the event buffer."""
    # Events are yielded via the message stream, but hooks can add
    # richer context (e.g. tool_starting with timing info)
    return {}  # Don't modify the tool call

async def post_tool_hook(
    input_data: dict, tool_use_id: str | None, context: HookContext
) -> dict:
    """Capture post-tool events."""
    return {}

# Add to ClaudeAgentOptions:
self._options.hooks = {
    "PreToolUse": [HookMatcher(hooks=[pre_tool_hook])],
    "PostToolUse": [HookMatcher(hooks=[post_tool_hook])],
}
```

### 3.2 Future Backends (sketch, not built in v2)

```python
# Copilot Agent Backend (future)
class CopilotAgentBackend(AgentBackend):
    def __init__(self) -> None:
        self._tool_adapter = CopilotToolAdapter()  # from v1 adapters

    async def configure(self, tool_defs, config) -> None:
        # Convert tools using CopilotToolAdapter
        # Build Copilot-specific session config
        ...

    async def execute(self, prompt: str) -> AsyncIterator[AgentEvent]:
        # Run Copilot session, yield normalized AgentEvents
        ...

    async def stop(self) -> None:
        # Copilot-specific interruption
        ...

# Stub backend for testing (no real SDK)
class StubAgentBackend(AgentBackend):
    """Yields canned events — useful for UI development and testing."""

    def __init__(self, events: list[AgentEvent] | None = None) -> None:
        self._events = events or []

    async def configure(self, tool_defs, config) -> None:
        pass  # Nothing to configure

    async def execute(self, prompt: str) -> AsyncIterator[AgentEvent]:
        for event in self._events:
            yield event

    async def stop(self) -> None:
        pass  # Nothing to stop
```

---

## 4. Agent Orchestrator

**File:** `src/agentml/agents/orchestrator.py`

The orchestrator manages a single agent run's lifecycle. It delegates all SDK-specific work to the `AgentBackend`. It never imports `claude_agent_sdk`.

```python
"""Agent orchestrator — manages an agent run lifecycle, SDK-agnostic."""

from __future__ import annotations

from datetime import UTC, datetime

from agentml.agents.backend import AgentBackend
from agentml.agents.prompts import build_system_prompt
from agentml.agents.types import AgentEvent, AgentRun, AgentRunConfig, RunStatus
from agentml.runtime.lab import LabEnvironment
from agentml.tools.server import collect_all_tools
from agentml.utils.ids import generate_id
from agentml.utils.logging import get_logger

logger = get_logger(__name__)


class AgentOrchestrator:
    """Manages one agent run using a pluggable AgentBackend.

    The orchestrator is responsible for:
    - Building the AgentRunConfig (system prompt, limits)
    - Collecting ToolDefs from v1
    - Passing tools + config to the backend
    - Driving the execute loop and appending events to AgentRun
    - Error handling and status transitions

    It does NOT know about Claude, Copilot, or any specific SDK.
    """

    def __init__(
        self,
        lab: LabEnvironment,
        backend: AgentBackend,
        *,
        max_turns: int = 50,
        max_budget_usd: float | None = None,
        permission_mode: str = "acceptEdits",
        cwd: str | None = None,
    ) -> None:
        self.lab = lab
        self.backend = backend
        self.max_turns = max_turns
        self.max_budget_usd = max_budget_usd
        self.permission_mode = permission_mode
        self.cwd = cwd
        self._run: AgentRun | None = None

    async def start(self, prompt: str, task_id: str | None = None) -> AgentRun:
        """Prepare an agent run: create run state, configure backend.

        Does not start execution — call execute() separately (usually in a background task).
        """
        run = AgentRun(
            task_id=task_id or generate_id(),
            prompt=prompt,
            status=RunStatus.RUNNING,
            started_at=datetime.now(UTC),
        )
        self._run = run

        # Build system prompt
        system_prompt = build_system_prompt(run)

        # Build config
        config = AgentRunConfig(
            system_prompt=system_prompt,
            max_turns=self.max_turns,
            max_budget_usd=self.max_budget_usd,
            permission_mode=self.permission_mode,
            cwd=self.cwd,
        )
        run.config = config

        # Collect v1 tool definitions (framework-agnostic)
        tool_defs = collect_all_tools(self.lab)

        # Configure the backend with tools and config
        await self.backend.configure(tool_defs, config)

        return run

    async def execute(self, run: AgentRun) -> None:
        """Execute the agent run (blocking). Call in a background task.

        Consumes the event stream from the backend and appends
        events to run.events. Updates run status on completion.
        """
        try:
            async for event in self.backend.execute(run.prompt):
                run.events.append(event)

                # Handle the result event
                if event.event_type == "result":
                    run.result = _result_from_event(event)
                    run.status = (
                        RunStatus.FAILED if event.data.get("is_error") else RunStatus.COMPLETED
                    )

                # Handle error events
                if event.event_type == "error":
                    run.status = RunStatus.FAILED
                    run.error = event.data.get("error", "Unknown error")

            run.completed_at = datetime.now(UTC)

        except Exception as e:
            run.status = RunStatus.FAILED
            run.error = str(e)
            run.completed_at = datetime.now(UTC)
            logger.error("agent_run_failed", run_id=run.id, error=str(e))

    async def stop(self) -> None:
        """Stop the running agent by interrupting the backend."""
        await self.backend.stop()
        if self._run:
            self._run.status = RunStatus.STOPPED
            self._run.completed_at = datetime.now(UTC)


def _result_from_event(event: AgentEvent) -> "AgentRunResult":
    """Extract AgentRunResult from a result event's data dict."""
    from agentml.agents.types import AgentRunResult

    return AgentRunResult(
        session_id=event.data.get("session_id"),
        total_cost_usd=event.data.get("cost_usd"),
        num_turns=event.data.get("turns", 0),
        duration_ms=event.data.get("duration_ms"),
        is_error=event.data.get("is_error", False),
    )
```

### 4.1 Backend Factory

**File:** `src/agentml/agents/factory.py`

Dispatches on the configured backend name to create the right `AgentBackend` instance.

```python
"""Agent backend factory — creates the right backend from config."""

from __future__ import annotations

from agentml.agents.backend import AgentBackend


def create_agent_backend(backend: str = "claude") -> AgentBackend:
    """Create an AgentBackend instance by name.

    Args:
        backend: Backend identifier ("claude", "stub", etc.)

    Returns:
        A configured AgentBackend instance.

    Raises:
        ValueError: If the backend name is unknown.
    """
    if backend == "claude":
        from agentml.agents.backends.claude import ClaudeAgentBackend

        return ClaudeAgentBackend()

    if backend == "stub":
        from agentml.agents.backends.stub import StubAgentBackend

        return StubAgentBackend()

    msg = f"Unknown agent backend: {backend}"
    raise ValueError(msg)
```

---

## 5. System Prompt Design

**File:** `src/agentml/agents/prompts.py`

Unchanged from the original — system prompts are SDK-agnostic by nature.

```python
"""System prompt templates for AgentML agent sessions."""

from agentml.agents.types import AgentRun


def build_system_prompt(run: AgentRun) -> str:
    """Build the system prompt for an agent session.

    This prompt is backend-agnostic — it describes the AgentML tools
    and workflow, not any specific SDK features.
    """
    hints_section = ""
    # Tool hints would be injected here (see section 10)

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
You have tools for running code, reading/writing files, and fetching web content.
Use them to run Python scripts for training, evaluation, etc.

## Workflow
1. **Search knowledge** first — have we learned anything about this problem before?
2. **Plan** your experimental approach (models, features, hyperparameters)
3. For each experiment:
   a. Call `create_experiment` with a clear hypothesis
   b. Write and run code (install packages as needed)
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

## 6. API Routes

**File:** `src/agentml/api/routers/agent.py`

Updated to use the backend factory. The router creates an `AgentOrchestrator` with whichever `AgentBackend` is configured.

```python
"""Agent router — start, monitor, and stop agent research sessions."""

import asyncio
import json
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from agentml.agents.factory import create_agent_backend
from agentml.agents.orchestrator import AgentOrchestrator
from agentml.agents.types import AgentRun, RunStatus
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

    # Create the backend from config (e.g. "claude", "stub")
    backend = create_agent_backend(settings.agent.backend)

    orchestrator = AgentOrchestrator(
        lab,
        backend,
        max_turns=body.max_turns,
        max_budget_usd=body.max_budget_usd,
        permission_mode=settings.agent.permission_mode,
        cwd=settings.agent.cwd,
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
        raise HTTPException(404, f"Run {run_id} not found")
    return _to_response(run)


@router.post("/runs/{run_id}/stop")
async def stop_run(run_id: str) -> dict:
    """Stop a running agent."""
    orchestrator = _orchestrators.get(run_id)
    if not orchestrator:
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
        total_cost_usd=run.result.total_cost_usd if run.result else None,
        num_turns=run.result.num_turns if run.result else 0,
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

## 7. Event Streaming

### How events flow (backend-agnostic)

```
AgentBackend.execute(prompt)
    │
    │  yields AgentEvent instances
    │  (normalized — same format regardless of backend)
    │
    ├── AgentEvent("tool_call", {tool, input})
    ├── AgentEvent("tool_result", {output})
    ├── AgentEvent("text", {text})
    ├── AgentEvent("error", {error})
    └── AgentEvent("result", {cost, turns, ...})
    │
    ▼  AgentOrchestrator.execute() appends to run.events[]
    │
    ▼  SSE endpoint polls run.events[]
    │
    ▼  Frontend EventSource receives events
```

The key improvement: the SSE layer and frontend only deal with `AgentEvent` — they never see SDK-specific types. Adding a new backend doesn't require any changes to the event streaming pipeline.

---

## 8. Frontend Changes

### 8.1 New types

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

### 8.2 New hooks

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

### 8.3 Agent page

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

### 8.4 Route addition

```tsx
// App.tsx — add:
import AgentPage from "@/pages/agent";

<Route path="agent" element={<AgentPage />} />
```

### 8.5 Nav item

Add "Agent" link in `frontend/src/components/layout/shell.tsx` nav.

---

## 9. Configuration

### Settings additions

**File:** `src/agentml/config/settings.py`

```python
class AgentSettings(BaseSettings):
    """Agent execution configuration."""
    backend: str = "claude"              # Which AgentBackend to use
    max_turns: int = 50                  # Max tool-use round trips
    max_budget_usd: float | None = None  # Max spend per run (None = unlimited)
    permission_mode: str = "acceptEdits" # Permission mode (backend-specific)
    cwd: str | None = None               # Working directory for code execution

class Settings(BaseSettings):
    ...
    agent: AgentSettings = Field(default_factory=AgentSettings)
```

### Environment variables

```bash
AGENTML__AGENT__BACKEND=claude
AGENTML__AGENT__MAX_TURNS=100
AGENTML__AGENT__MAX_BUDGET_USD=5.00
```

---

## 10. Task-Level Tool Hints

Tool hints let users tell the agent about data sources or domain-specific tools it should create.

### How they work

1. User submits hints via the UI (name, description, source URL)
2. Hints are injected into the system prompt as instructions
3. The agent uses its built-in tools to read the source and write loader code
4. The agent naturally creates reusable code — no dynamic MCP tool creation needed

This is the key simplification: **the agent SDK can already read URLs and write code.** We don't need a `create_tool` meta-tool. We just need to tell the agent about the data sources in the prompt.

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
    hints += "\nFetch these sources if needed, then write appropriate data loading code.\n"
```

---

## 11. File-by-File Change Map

### New files

| File | Purpose |
|---|---|
| `src/agentml/agents/types.py` | `AgentRun`, `AgentEvent`, `AgentRunConfig`, `AgentRunResult`, `RunStatus` |
| `src/agentml/agents/backend.py` | `AgentBackend` ABC (the port) |
| `src/agentml/agents/factory.py` | `create_agent_backend()` factory function |
| `src/agentml/agents/orchestrator.py` | `AgentOrchestrator` (SDK-agnostic) |
| `src/agentml/agents/prompts.py` | System prompt template |
| `src/agentml/agents/backends/__init__.py` | Backends package init |
| `src/agentml/agents/backends/claude.py` | `ClaudeAgentBackend` (Claude Agent SDK adapter) |
| `src/agentml/agents/backends/stub.py` | `StubAgentBackend` (for testing & UI dev) |
| `src/agentml/api/routers/agent.py` | Agent run API routes + SSE |
| `frontend/src/pages/agent.tsx` | Agent page |
| `frontend/src/hooks/use-agent.ts` | Agent runs hooks |
| `frontend/src/hooks/use-agent-events.ts` | SSE event stream hook |
| `frontend/src/components/agent/agent-prompt-form.tsx` | Prompt + tool hints form |
| `frontend/src/components/agent/agent-run-view.tsx` | Live agent run view |
| `frontend/src/components/agent/event-feed.tsx` | Event feed component |
| `frontend/src/components/agent/run-summary.tsx` | Run summary component |
| `tests/unit/test_agent_backend.py` | Unit tests for `AgentBackend` + `StubAgentBackend` |
| `tests/unit/test_orchestrator.py` | Orchestrator tests (using `StubAgentBackend`) |
| `tests/unit/test_claude_backend.py` | Claude backend tests (mocked SDK) |
| `tests/e2e/test_agent_run.py` | E2E agent run test |

### Modified files

| File | Change |
|---|---|
| `src/agentml/api/app.py` | Include agent router |
| `src/agentml/config/settings.py` | Add `AgentSettings` with `backend` field |
| `pyproject.toml` | Add `sse-starlette` dependency |
| `frontend/src/types.ts` | Add `AgentRun`, `AgentEvent`, `ToolHint` types |
| `frontend/src/App.tsx` | Add agent route |
| `frontend/src/components/layout/shell.tsx` | Add agent nav item |

---

## 12. Implementation Steps

```
Step 1 — Dependencies                         ~15 min
├── Add sse-starlette to pyproject.toml
└── npm install (if any new frontend deps)

Step 2 — Domain types                         ~30 min
├── Create agents/types.py
│   ├── RunStatus enum
│   ├── AgentEvent dataclass
│   ├── AgentRunConfig dataclass
│   ├── AgentRunResult dataclass
│   └── AgentRun dataclass
└── Unit tests for types

Step 3 — Agent backend interface              ~30 min
├── Create agents/backend.py (AgentBackend ABC)
├── Create agents/backends/__init__.py
├── Create agents/backends/stub.py (StubAgentBackend)
└── Unit test StubAgentBackend

Step 4 — Claude agent backend                 ~1.5 hours
├── Create agents/backends/claude.py
│   ├── ClaudeAgentBackend class
│   ├── Uses ClaudeToolAdapter from v1
│   └── Claude message → AgentEvent mapping
├── Create agents/factory.py
└── Unit tests (mocked ClaudeSDKClient)

Step 5 — Orchestrator                          ~1 hour
├── Create agents/orchestrator.py
│   ├── AgentOrchestrator (SDK-agnostic)
│   └── Uses AgentBackend interface
├── Create agents/prompts.py
└── Unit tests (using StubAgentBackend — no SDK needed)

Step 6 — API routes                            ~1.5 hours
├── Create api/routers/agent.py
│   ├── POST /agent/run (uses backend factory)
│   ├── GET /agent/runs, /agent/runs/{id}
│   ├── POST /agent/runs/{id}/stop
│   └── GET /agent/runs/{id}/events (SSE)
├── Wire into app.py
└── E2E test

Step 7 — Configuration                        ~30 min
├── Add AgentSettings (with backend field) to settings.py
└── Wire into agent router

Step 8 — Frontend: types & hooks              ~1 hour
├── Add types to types.ts
├── Create use-agent.ts
└── Create use-agent-events.ts

Step 9 — Frontend: agent page                 ~2-3 hours
├── Create agent-prompt-form.tsx
├── Create agent-run-view.tsx
├── Create event-feed.tsx
├── Create run-summary.tsx
├── Create pages/agent.tsx
├── Add route to App.tsx
└── Add nav item to shell.tsx

Step 10 — Integration test                     ~1 hour
├── Start backend + frontend
├── Submit a prompt via UI
├── Verify: events stream, experiments appear, knowledge saved
└── Test stop button

Step 11 — Polish                               ~1 hour
├── Error handling edge cases
├── Loading states
└── Cleanup
```

**Total estimated time: ~10-12 hours**

---

## 13. End-to-End Example: Boston Housing

### User submits via UI

**Prompt:**
> Improve the accuracy of the Boston housing prediction problem. Start with a linear regression baseline, then try more advanced models. Target: R² > 0.85.

**Tool hints:**
| Name | Description | Source |
|---|---|---|
| `fetch_dataset` | Load the Boston housing dataset | `https://scikit-learn.org/1.0/modules/generated/sklearn.datasets.load_boston.html` |

### What happens under the hood

```
1. POST /agent/run → agent router
2. create_agent_backend("claude") → ClaudeAgentBackend
3. AgentOrchestrator(lab, backend) created
4. orchestrator.start(prompt)
   ├── build_system_prompt(run) → system prompt string
   ├── collect_all_tools(lab) → [ToolDef, ToolDef, ...] (11 tools)
   └── backend.configure(tool_defs, config)
       ├── ClaudeToolAdapter.create_server("agentml", tool_defs) → MCP server
       └── ClaudeSDKClient(options) initialized
5. asyncio.create_task(orchestrator.execute(run))
   └── backend.execute(prompt) → yields AgentEvent stream
       └── ClaudeSDKClient manages the conversation
```

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

## Appendix: Full Adapter Pattern (v1 + v2 Together)

The hexagonal architecture is now complete across both tools and agent sessions:

```
                    ┌──────────────────────────────────┐
                    │        AgentML Core Domain        │
                    │  ToolDef, ToolResult, AgentEvent   │
                    │  AgentRun, AgentRunConfig          │
                    │  Experiment, Knowledge, Task       │
                    └──────────┬───────────────────────┘
                               │
              ┌────────────────┼────────────────┐
              │                │                │
    ┌─────────▼──────┐  ┌─────▼─────┐  ┌───────▼───────┐
    │  ToolAdapter   │  │ AgentBack-│  │ TrackingConn- │
    │  (v1 port)     │  │ end (v2)  │  │ ector (exist) │
    └─────┬──────────┘  └─────┬─────┘  └───────┬───────┘
          │                   │                 │
   ┌──────▼──────┐    ┌──────▼──────┐   ┌──────▼──────┐
   │  Claude     │    │  Claude     │   │  MLflow     │
   │  ToolAdapter│    │  AgentBack- │   │  Tracker    │
   │  (@tool)    │    │  end (SDK)  │   │             │
   └─────────────┘    └─────────────┘   └─────────────┘
   ┌─────────────┐    ┌─────────────┐   ┌─────────────┐
   │  (future)   │    │  (future)   │   │  File       │
   │  Copilot    │    │  Copilot    │   │  Tracker    │
   │  ToolAdapter│    │  AgentBack- │   │             │
   └─────────────┘    │  end        │   └─────────────┘
                      └─────────────┘
```

| Layer | v1 (Tools) | v2 (Agent Sessions) |
|---|---|---|
| **Core abstraction** | `ToolDef` + `ToolResult` | `AgentBackend` + `AgentEvent` |
| **Registry/collection** | `ToolRegistry`, `collect_all_tools()` | `create_agent_backend()` factory |
| **Adapter interface** | `ToolAdapter` ABC | `AgentBackend` ABC |
| **Claude impl** | `ClaudeToolAdapter` | `ClaudeAgentBackend` |
| **Stub/test impl** | (call handler directly) | `StubAgentBackend` |
| **Config dispatch** | `adapter="claude"` in server.py | `agent.backend="claude"` in settings |
| **SDK-free testing** | Test `ToolDef.handler()` directly | Test orchestrator with `StubAgentBackend` |

---

## Appendix: What We Removed vs. Original Plan

The original plan included complexity that the adapter pattern and SDK make unnecessary:

| Original concept | Current approach | Simplification |
|---|---|---|
| Orchestrator directly uses `ClaudeSDKClient` | Orchestrator uses `AgentBackend` ABC | SDK-agnostic orchestrator |
| Hard-coded `AGENTML_TOOLS` list | `ClaudeToolAdapter.tool_names_prefixed()` | Tool names derived from adapter |
| `_message_to_event()` in orchestrator | `_message_to_events()` in `ClaudeAgentBackend` | SDK-specific parsing stays in backend |
| Claude imports in orchestrator | Zero SDK imports in orchestrator | Clean separation of concerns |
| Testing requires mocking `ClaudeSDKClient` | `StubAgentBackend` for orchestrator tests | SDK-free orchestrator tests |
| Custom agent loop | `ClaudeSDKClient` handles this | No agent loop code at all |
| `execute_code` / `install_packages` tools | Built-in `Bash` tool (Claude SDK) | No sandbox tools needed |
| `create_tool` dynamic meta-tool | Prompt hints instead | No dynamic tool creation |

**Net result:** The orchestrator is ~50 lines of SDK-agnostic code. All Claude-specific logic lives in `ClaudeAgentBackend`. Adding a new agent SDK means implementing one class — no changes to orchestrator, API routes, frontend, or tests.
