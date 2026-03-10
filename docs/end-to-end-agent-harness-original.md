# End-to-End Agent Harness — Implementation Plan

> **Goal:** Transform AgentML from a stub-driven experiment runner into an autonomous ML research agent powered by the Claude Agents SDK, with well-defined tools, code execution, and a live UI feedback loop.

---

## Table of Contents

1. [Current State Analysis](#1-current-state-analysis)
2. [Architecture Vision](#2-architecture-vision)
3. [Phase 1 — AgentML Built-in Tools](#3-phase-1--agentml-built-in-tools)
4. [Phase 2 — Code Execution Environment](#4-phase-2--code-execution-environment)
5. [Phase 3 — Claude Agents SDK Integration](#5-phase-3--claude-agents-sdk-integration)
6. [Phase 4 — Experiment-Specific Tools & Dynamic Tool Creation](#6-phase-4--experiment-specific-tools--dynamic-tool-creation)
7. [Phase 5 — Agent Run Lifecycle & UI](#7-phase-5--agent-run-lifecycle--ui)
8. [Phase 6 — End-to-End: Boston Housing Example](#8-phase-6--end-to-end-boston-housing-example)
9. [File-by-File Change Map](#9-file-by-file-change-map)
10. [Migration & Sequencing](#10-migration--sequencing)

---

## 1. Current State Analysis

### What exists today

| Component | Status | Location |
|---|---|---|
| **Agent interface** | ABC with `run(task, lab) → TaskResult` | `src/agentml/interfaces/agent.py` |
| **StubAgent** | Hardcoded mock — no LLM, no tools | `src/agentml/agents/stub_agent.py` |
| **ToolRuntime interface** | ABC with `register_tool`, `list_tools`, `call_tool` | `src/agentml/interfaces/tool_runtime.py` |
| **ToolRuntime impl** | **None** — interface exists but no concrete adapter | — |
| **Sandbox interface** | ABC with `execute(code)`, `install_packages`, `cleanup` | `src/agentml/interfaces/sandbox.py` |
| **LocalSandbox** | Executes Python via subprocess in tmpdir | `src/agentml/sandbox/local.py` |
| **LabEnvironment** | DI container — no `tool_runtime` field | `src/agentml/runtime/lab.py` |
| **ExperimentService** | State machine orchestration (create/run/complete/fail) | `src/agentml/runtime/experiment_service.py` |
| **TrackingConnector** | File + MLflow + Noop adapters | `src/agentml/tracking/` |
| **MemoryStore** | Local JSON keyword search | `src/agentml/storage/local_memory.py` |
| **Config** | `llm.provider` / `llm.model` fields exist but unused | `src/agentml/config/settings.py` |
| **Frontend** | React dark UI with tasks/experiments/knowledge pages | `frontend/src/` |
| **API** | REST routes for tasks (sync stub), experiments, knowledge, tracking | `src/agentml/api/routers/` |

### Key gaps

1. **No real agent** — `StubAgent` hardcodes a single experiment, no LLM interaction
2. **No tool registry** — `ToolRuntime` interface exists but has no implementation, and is not wired into `LabEnvironment`
3. **No tool definitions** — No concrete tools (create_experiment, run_code, etc.) are defined
4. **No agent loop** — No iterative plan→act→observe cycle; tasks complete synchronously
5. **No streaming / async agent runs** — Frontend can't observe a running agent
6. **No dynamic tool creation** — Agent can't define experiment-specific tools at runtime
7. **Sandbox is disconnected** — `LocalSandbox` exists but agent doesn't use it

---

## 2. Architecture Vision

```
┌─────────────────────────────────────────────────────────────┐
│                        Frontend (React)                      │
│  Task form → "Improve Boston Housing prediction accuracy"   │
│  + data source hints, constraints                            │
│  Live: agent status, experiment cards, knowledge feed        │
└────────────────────────┬────────────────────────────────────┘
                         │ REST + SSE/WebSocket
┌────────────────────────▼────────────────────────────────────┐
│                     FastAPI Backend                           │
│                                                              │
│  POST /agent/run  ──→  AgentOrchestrator                    │
│  GET  /agent/status/{run_id}                                │
│  GET  /agent/events/{run_id}  (SSE stream)                  │
│                                                              │
│  AgentOrchestrator                                           │
│  ├── Claude Agents SDK (anthropic.Agent)                    │
│  ├── Built-in Tools (AgentML tools)                         │
│  │   ├── create_experiment()                                │
│  │   ├── run_experiment()                                   │
│  │   ├── view_results()                                     │
│  │   ├── compare_models()                                   │
│  │   ├── write_knowledge()                                  │
│  │   ├── search_knowledge()                                 │
│  │   └── log_metrics()                                      │
│  ├── Code Execution Tools                                    │
│  │   ├── execute_code()                                     │
│  │   ├── install_packages()                                 │
│  │   └── read_execution_output()                            │
│  ├── Experiment-Specific Tools (dynamic, agent-created)     │
│  │   ├── fetch_dataset()    (user-hinted or agent-built)    │
│  │   └── custom_evaluate()  (agent-defined)                 │
│  └── LabEnvironment (all backends)                           │
│       ├── experiment_store                                   │
│       ├── memory_store                                       │
│       ├── tracking (MLflow / File)                           │
│       ├── sandbox (Local → Modal)                            │
│       ├── artifact_store                                     │
│       └── tool_runtime                                       │
└──────────────────────────────────────────────────────────────┘
```

### Key principle: Three layers of tools

| Layer | Description | Lifetime | Examples |
|---|---|---|---|
| **Built-in tools** | AgentML platform tools the agent always has | Global, static | `create_experiment`, `run_experiment`, `write_knowledge`, `compare_models` |
| **Code execution tools** | Let the agent write, run, and inspect arbitrary code | Global, static | `execute_code`, `install_packages` |
| **Experiment-specific tools** | Created dynamically per task/experiment run, either from user hints or agent-authored | Per agent run | `fetch_boston_data`, `evaluate_rmse`, custom data loaders |

---

## 3. Phase 1 — AgentML Built-in Tools

> **Outcome:** A concrete `ToolRegistry` and a full set of platform tools that wrap `LabEnvironment` services.

### 3.1 Implement `ToolRegistry` (concrete `ToolRuntime`)

**File:** `src/agentml/tools/registry.py` (new)

```python
"""Concrete tool runtime — registers and dispatches tools."""

from collections.abc import Callable
from typing import Any
from dataclasses import dataclass, field
from agentml.interfaces.tool_runtime import ToolRuntime


@dataclass
class ToolDef:
    """Internal tool descriptor."""
    name: str
    fn: Callable[..., Any]
    description: str
    parameters_schema: dict[str, Any]  # JSON Schema for args


class ToolRegistry(ToolRuntime):
    """In-memory tool registry with schema introspection."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolDef] = {}

    def register_tool(
        self, name: str, fn: Callable[..., Any], *, description: str = "",
        parameters_schema: dict[str, Any] | None = None,
    ) -> None: ...

    def list_tools(self) -> list[dict[str, Any]]: ...

    async def call_tool(self, name: str, **kwargs: Any) -> Any: ...

    def to_claude_tools(self) -> list[dict[str, Any]]:
        """Export tools in Claude Agents SDK tool format."""
        ...
```

### 3.2 Define Built-in Tools

**File:** `src/agentml/tools/builtin.py` (new)

Each tool is a plain async function that receives `LabEnvironment` via closure. We register them at startup.

| Tool name | Input | What it does | Returns |
|---|---|---|---|
| `create_experiment` | `task_id`, `hypothesis`, `config` | Creates `Experiment` via `ExperimentService.create()` | `experiment_id` |
| `run_experiment` | `experiment_id`, `code` | Transitions to RUNNING, executes code in sandbox, captures metrics, transitions to COMPLETED/FAILED | `{experiment_id, status, metrics, stdout, stderr}` |
| `view_results` | `experiment_id` | Loads experiment + metrics from store & tracking | `{experiment, metrics}` |
| `compare_models` | `experiment_ids: list[str]` | Loads multiple experiments, computes comparison table | `{comparison: [{id, metrics, config}]}` |
| `write_knowledge` | `context`, `claim`, `action?`, `confidence?`, `evidence_ids?` | Writes `KnowledgeAtom` to `MemoryStore` | `atom_id` |
| `search_knowledge` | `query`, `limit?` | Searches `MemoryStore` for relevant atoms | `[KnowledgeAtom]` |
| `log_metrics` | `experiment_id`, `metrics: dict` | Logs to `TrackingConnector` | `ok` |
| `log_params` | `experiment_id`, `params: dict` | Logs to `TrackingConnector` | `ok` |
| `list_experiments` | `task_id?` | Lists experiments from store | `[Experiment]` |

```python
# src/agentml/tools/builtin.py

def register_builtin_tools(registry: ToolRegistry, lab: LabEnvironment) -> None:
    """Register all AgentML platform tools."""

    service = ExperimentService(lab)

    async def create_experiment(
        task_id: str, hypothesis: str, variables: dict | None = None, config: dict | None = None
    ) -> dict:
        exp = Experiment(
            task_id=task_id,
            hypothesis=Hypothesis(description=hypothesis, variables=variables or {}),
            config=config or {},
        )
        exp_id = await service.create(exp)
        return {"experiment_id": exp_id}

    registry.register_tool(
        "create_experiment",
        create_experiment,
        description="Create a new experiment with a hypothesis to test.",
        parameters_schema={...},
    )

    # ... similarly for all other tools
```

### 3.3 Wire `ToolRuntime` into `LabEnvironment`

**File:** `src/agentml/runtime/lab.py`

```python
@dataclass
class LabEnvironment:
    compute: ComputeBackend
    sandbox: Sandbox
    experiment_store: ExperimentStore
    artifact_store: ArtifactStore
    memory_store: MemoryStore
    tracking: TrackingConnector
    tool_runtime: ToolRuntime  # ← ADD
```

**File:** `src/agentml/api/deps.py` — create `ToolRegistry`, call `register_builtin_tools`, pass into `LabEnvironment`.

### 3.4 Tool JSON Schema Generation

Auto-generate `parameters_schema` from function type hints using `inspect.signature` + `typing.get_type_hints`. This is needed for Claude's tool-use protocol.

**File:** `src/agentml/tools/schema.py` (new)

```python
def function_to_json_schema(fn: Callable) -> dict[str, Any]:
    """Introspect an async function and produce a JSON Schema for its parameters."""
    ...
```

---

## 4. Phase 2 — Code Execution Environment

> **Outcome:** The agent can write arbitrary Python, execute it in a sandbox, inspect results, and iterate.

### 4.1 Code Execution Tools

**File:** `src/agentml/tools/code_execution.py` (new)

| Tool name | Input | What it does | Returns |
|---|---|---|---|
| `execute_code` | `code: str`, `language?: str` | Runs code via `Sandbox.execute()` | `{stdout, stderr, exit_code, duration_ms, artifacts}` |
| `install_packages` | `packages: list[str]` | Installs via `Sandbox.install_packages()` | `{stdout, stderr, exit_code}` |
| `save_artifact` | `name: str`, `data: str`, `content_type?` | Saves to `ArtifactStore` | `{artifact_id, path}` |

```python
def register_code_tools(registry: ToolRegistry, lab: LabEnvironment) -> None:
    async def execute_code(code: str, language: str = "python") -> dict:
        result = await lab.sandbox.execute(code, language=language)
        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "exit_code": result.exit_code,
            "duration_ms": result.duration_ms,
        }
    registry.register_tool("execute_code", execute_code, description="...")
```

### 4.2 Enhanced LocalSandbox

The current `LocalSandbox` creates a fresh tmpdir per execution. For multi-step agent runs, we need:

1. **Persistent working directory** per agent run — so the agent can write a file, then import it later
2. **File I/O** — agent should be able to write data files and read outputs
3. **Virtual environment isolation** — `install_packages` should use a venv, not system pip

**File:** `src/agentml/sandbox/local.py` — Enhance:

```python
class LocalSandbox(Sandbox):
    def __init__(self, timeout: float = 30.0, workdir: Path | None = None) -> None:
        self.timeout = timeout
        self._workdir = workdir or Path(tempfile.mkdtemp(prefix="agentml_sandbox_"))
        self._venv_created = False

    async def execute(self, code: str, *, language: str = "python") -> ExecutionResult:
        """Execute code in the persistent working directory."""
        script_path = self._workdir / f"step_{generate_id()}.py"
        script_path.write_text(code)
        # Run with venv python if available
        python = self._venv_python or "python"
        ...

    async def write_file(self, path: str, content: str) -> str:
        """Write a file to the sandbox working directory."""
        ...

    async def read_file(self, path: str) -> str:
        """Read a file from the sandbox working directory."""
        ...

    async def list_files(self, pattern: str = "*") -> list[str]:
        """List files in the sandbox working directory."""
        ...
```

### 4.3 Sandbox interface expansion

**File:** `src/agentml/interfaces/sandbox.py` — Add optional `write_file`, `read_file`, `list_files` methods (with default `NotImplementedError` so existing impls don't break, or add them as a mixin/sub-interface).

### 4.4 Future: Modal / Docker sandbox swap

The `Sandbox` interface already abstracts this. Later phases add:
- `ModalSandbox` → executes in Modal's sandboxed container
- `DockerSandbox` → executes in a local Docker container
- Config: `sandbox.backend: "local" | "modal" | "docker"`

---

## 5. Phase 3 — Claude Agents SDK Integration

> **Outcome:** Replace `StubAgent` with a real Claude-powered agent that uses the Agents SDK's tool-use loop.

### 5.1 Dependency

```toml
# pyproject.toml [project.optional-dependencies]
anthropic = ["anthropic>=0.80"]
```

The `anthropic` package includes the Agents SDK (`anthropic.Agent`, tool definitions, etc.).

### 5.2 `ClaudeAgent` implementation

**File:** `src/agentml/agents/claude_agent.py` (new)

```python
"""Claude agent — real LLM-powered agent using Anthropic Agents SDK."""

import anthropic
from anthropic.types import ToolUseBlock

from agentml.interfaces.agent import Agent
from agentml.core.task import Task, TaskResult
from agentml.runtime.lab import LabEnvironment


class ClaudeAgent(Agent):
    """Agent powered by Claude via the Anthropic Agents SDK."""

    def __init__(self, model: str = "claude-sonnet-4-20250514", api_key: str = "") -> None:
        self.model = model
        self.client = anthropic.AsyncAnthropic(api_key=api_key) if api_key else anthropic.AsyncAnthropic()

    async def run(self, task: Task, lab: LabEnvironment) -> TaskResult:
        """Execute the agentic loop: plan → tool calls → observe → repeat."""

        # Convert registered tools to Claude format
        tools = lab.tool_runtime.to_claude_tools()

        system_prompt = self._build_system_prompt(task)
        messages = [{"role": "user", "content": task.prompt}]

        # Agentic loop
        while True:
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                system=system_prompt,
                tools=tools,
                messages=messages,
            )

            # Check for tool use
            if response.stop_reason == "tool_use":
                tool_results = []
                for block in response.content:
                    if isinstance(block, ToolUseBlock):
                        result = await lab.tool_runtime.call_tool(
                            block.name, **block.input
                        )
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": json.dumps(result),
                        })
                messages.append({"role": "assistant", "content": response.content})
                messages.append({"role": "user", "content": tool_results})
                continue

            # Agent finished — extract final answer
            final_text = "".join(
                b.text for b in response.content if hasattr(b, "text")
            )
            break

        return self._parse_result(task, final_text)
```

### 5.3 System prompt design

The system prompt is critical. It must:

1. Explain the agent's role (autonomous ML researcher)
2. List available tools with clear descriptions
3. Explain the experiment lifecycle (create → run → view → compare → knowledge)
4. Provide the user's task context and constraints
5. Encourage iterative experimentation

**File:** `src/agentml/agents/prompts.py` (new)

```python
SYSTEM_PROMPT_TEMPLATE = """
You are an autonomous ML research agent operating within AgentML.

## Your capabilities
You can create experiments, write and execute Python code, track metrics,
compare models, and record learnings as knowledge atoms.

## Workflow
1. Understand the research goal
2. Plan your approach (what models/features to try)
3. Create experiments with clear hypotheses
4. Write and execute code to train models and evaluate them
5. Log metrics and compare results
6. Record what you learn as knowledge atoms
7. Iterate until you've meaningfully improved on the objective

## Available tools
{tool_descriptions}

## Current task
{task_context}

## Important
- Always create an experiment BEFORE running code for it
- Log metrics after each experiment
- Write knowledge atoms when you discover something meaningful
- Compare models periodically to assess progress
- Be systematic: change one thing at a time
"""
```

### 5.4 Agent selection in config & deps

**File:** `src/agentml/config/settings.py`

```python
class LLMSettings(BaseSettings):
    provider: str = "stub"          # "stub" | "anthropic"
    model: str = "stub"             # "claude-sonnet-4-20250514", etc.
    api_key: str = ""               # AGENTML__LLM__API_KEY
    max_tokens: int = 4096
    max_agent_turns: int = 50       # Safety limit on agent loop iterations
```

**File:** `src/agentml/api/deps.py` — add `_build_agent(settings) → Agent`:

```python
def _build_agent(settings: Settings) -> Agent:
    if settings.llm.provider == "anthropic":
        from agentml.agents.claude_agent import ClaudeAgent
        return ClaudeAgent(model=settings.llm.model, api_key=settings.llm.api_key)
    from agentml.agents.stub_agent import StubAgent
    return StubAgent()
```

### 5.5 Add `agent` to `LabEnvironment`

```python
@dataclass
class LabEnvironment:
    compute: ComputeBackend
    sandbox: Sandbox
    experiment_store: ExperimentStore
    artifact_store: ArtifactStore
    memory_store: MemoryStore
    tracking: TrackingConnector
    tool_runtime: ToolRuntime
    agent: Agent                    # ← ADD
```

---

## 6. Phase 4 — Experiment-Specific Tools & Dynamic Tool Creation

> **Outcome:** Users can provide hints (data sources, evaluation criteria), and the agent can create its own tools at runtime.

### 6.1 Task-level tool hints (user-provided)

Extend the `Task` model and API to accept tool hints:

**File:** `src/agentml/core/task.py`

```python
@dataclass
class ToolHint:
    """A hint for an experiment-specific tool the agent should create."""
    name: str               # e.g. "fetch_dataset"
    description: str        # e.g. "Load the Boston housing dataset"
    source: str             # e.g. URL, package path, or instructions
    code_template: str = "" # Optional starter code

@dataclass
class Task:
    ...
    tool_hints: list[ToolHint] = field(default_factory=list)
```

**API change:** `POST /agent/run` body:

```json
{
  "prompt": "Improve the accuracy of the Boston housing prediction problem",
  "tool_hints": [
    {
      "name": "fetch_dataset",
      "description": "Load training data for Boston housing",
      "source": "https://scikit-learn.org/1.0/modules/generated/sklearn.datasets.load_boston.html",
      "code_template": ""
    }
  ]
}
```

### 6.2 Dynamic tool creation by the agent

Give the agent a meta-tool: `create_tool`.

| Tool name | Input | What it does |
|---|---|---|
| `create_tool` | `name`, `description`, `code` | Registers a new tool (Python function as a string) in the `ToolRegistry` for the current run |

```python
async def create_tool(name: str, description: str, code: str) -> dict:
    """
    Agent writes Python code defining a function,
    we execute it to get the callable, then register it.
    """
    # Execute code in sandbox to define the function
    wrapper_code = f"""
{code}

# The function must be named '{name}'
import json
result = {name}()
print(json.dumps(result))
"""
    # Validate it runs at least once
    result = await lab.sandbox.execute(wrapper_code)
    if result.exit_code != 0:
        return {"error": f"Tool code failed: {result.stderr}"}

    # Register as a tool that executes the code each time
    async def dynamic_tool(**kwargs) -> dict:
        call_code = f"""
{code}
import json
result = {name}(**{kwargs!r})
print(json.dumps(result))
"""
        exec_result = await lab.sandbox.execute(call_code)
        return json.loads(exec_result.stdout) if exec_result.exit_code == 0 else {"error": exec_result.stderr}

    registry.register_tool(name, dynamic_tool, description=description)
    return {"status": "created", "tool_name": name}
```

### 6.3 Tool hint → auto-prompt injection

When the agent starts, tool hints are injected into the system prompt:

```
## Experiment-specific context
The user has provided the following hints for tools you should create:

1. **fetch_dataset**: Load training data for Boston housing
   Source: https://scikit-learn.org/1.0/modules/generated/sklearn.datasets.load_boston.html
   → Use `create_tool` to build this as a reusable tool, or use `execute_code` directly.
```

---

## 7. Phase 5 — Agent Run Lifecycle & UI

> **Outcome:** Agent runs asynchronously, streams events, and the UI shows live progress.

### 7.1 AgentRun model

**File:** `src/agentml/core/agent_run.py` (new)

```python
@dataclass
class AgentRun:
    id: str = field(default_factory=generate_id)
    task_id: str = ""
    status: AgentRunStatus = AgentRunStatus.PENDING  # pending/running/completed/failed
    events: list[AgentEvent] = field(default_factory=list)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    result: TaskResult | None = None
    error: str | None = None

@dataclass
class AgentEvent:
    """An event emitted during an agent run."""
    id: str = field(default_factory=generate_id)
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    event_type: str = ""     # "tool_call", "tool_result", "thinking", "experiment_created", etc.
    data: dict[str, Any] = field(default_factory=dict)
```

### 7.2 Agent run API routes

**File:** `src/agentml/api/routers/agent.py` (new)

| Method | Path | Description |
|---|---|---|
| `POST` | `/agent/run` | Start an agent run (async background task) |
| `GET` | `/agent/runs` | List all agent runs |
| `GET` | `/agent/runs/{run_id}` | Get agent run status + events |
| `GET` | `/agent/runs/{run_id}/events` | SSE stream of agent events |
| `POST` | `/agent/runs/{run_id}/stop` | Stop a running agent |

```python
@router.post("/run")
async def start_agent_run(body: StartAgentRunRequest, request: Request) -> AgentRunResponse:
    """Start an async agent run."""
    lab = request.app.state.lab
    task = Task(prompt=body.prompt, tool_hints=body.tool_hints or [])

    # Create run
    run = AgentRun(task_id=task.id)
    _runs[run.id] = run

    # Launch in background
    asyncio.create_task(_execute_agent_run(run, task, lab))

    return AgentRunResponse(id=run.id, status=run.status.value)

@router.get("/runs/{run_id}/events")
async def stream_events(run_id: str, request: Request) -> EventSourceResponse:
    """SSE stream of agent events."""
    ...
```

### 7.3 Event emission from tools

Each tool call emits an `AgentEvent` so the UI can track what's happening:

```python
# In the agent loop, after each tool call:
run.events.append(AgentEvent(
    event_type="tool_call",
    data={"tool": tool_name, "input": tool_input},
))
run.events.append(AgentEvent(
    event_type="tool_result",
    data={"tool": tool_name, "output": tool_result},
))
```

### 7.4 Frontend changes

#### New types

**File:** `frontend/src/types.ts`

```typescript
export interface AgentRun {
  id: string;
  task_id: string;
  status: "pending" | "running" | "completed" | "failed";
  events: AgentEvent[];
  started_at: string | null;
  completed_at: string | null;
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

#### New pages & components

| Component | Purpose |
|---|---|
| `pages/agent.tsx` | Main agent page — prompt input, tool hints, start button |
| `components/agent/agent-prompt-form.tsx` | Rich form: prompt + tool hints (add/remove) |
| `components/agent/agent-run-view.tsx` | Live view of a running agent |
| `components/agent/event-feed.tsx` | Scrolling feed of agent events |
| `components/agent/experiment-cards.tsx` | Cards showing experiments created during the run |

#### New hooks

| Hook | Purpose |
|---|---|
| `use-agent-runs.ts` | SWR hook for `/agent/runs` |
| `use-agent-events.ts` | SSE subscription to `/agent/runs/{id}/events` |

#### Route addition

```tsx
// App.tsx
<Route path="agent" element={<AgentPage />} />
```

---

## 8. Phase 6 — End-to-End: Boston Housing Example

> **Validation scenario:** User submits "Improve the accuracy of the Boston housing prediction problem" with a data source hint.

### User flow

1. **User opens Agent page** in UI
2. **Fills prompt:** "Improve the accuracy of the Boston housing prediction problem. Start with a linear regression baseline, then try more advanced models."
3. **Adds tool hint:**
   - Name: `fetch_dataset`
   - Description: "Load the Boston housing dataset from scikit-learn"
   - Source: `https://scikit-learn.org/1.0/modules/generated/sklearn.datasets.load_boston.html`
4. **Clicks "Start Research"**

### What the agent does (expected sequence)

```
1. Agent receives task + tool hints
2. Agent calls create_tool("fetch_dataset", ..., code that loads Boston data)
3. Agent calls create_experiment(task_id, "Linear regression baseline", {"model": "LinearRegression"})
4. Agent calls execute_code("""
     from sklearn.datasets import load_boston
     from sklearn.linear_model import LinearRegression
     from sklearn.model_selection import train_test_split
     from sklearn.metrics import mean_squared_error, r2_score
     import json

     X, y = load_boston(return_X_y=True)
     X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2)
     model = LinearRegression()
     model.fit(X_train, y_train)
     preds = model.predict(X_test)
     print(json.dumps({
         "mse": mean_squared_error(y_test, preds),
         "r2": r2_score(y_test, preds)
     }))
   """)
5. Agent calls log_metrics(exp_id, {"mse": 24.3, "r2": 0.72})
6. Agent calls write_knowledge("Baseline linear regression", "R²=0.72, MSE=24.3", ...)
7. Agent calls create_experiment(task_id, "Random Forest", {"model": "RandomForestRegressor"})
8. Agent calls execute_code(... random forest code ...)
9. Agent calls log_metrics(...)
10. Agent calls compare_models([exp1_id, exp2_id])
11. Agent calls write_knowledge("Random Forest improves over Linear Regression", ...)
12. ... continues with feature engineering, hyperparameter tuning, etc.
13. Agent produces final TaskResult with best_experiment_id and summary
```

### What the UI shows

- **Status badge:** "Agent Running" (animated)
- **Event feed:** Live stream of tool calls and results
- **Experiment cards:** Appear as agent creates them, metrics update live
- **Knowledge feed:** New atoms appear as agent records learnings
- **Comparison table:** Auto-updated as agent compares models
- **Final summary:** Displayed when agent completes

---

## 9. File-by-File Change Map

### New files

| File | Purpose |
|---|---|
| `src/agentml/tools/__init__.py` | Package init |
| `src/agentml/tools/registry.py` | `ToolRegistry` — concrete `ToolRuntime` impl |
| `src/agentml/tools/schema.py` | JSON Schema generation from function signatures |
| `src/agentml/tools/builtin.py` | AgentML platform tools (create_experiment, etc.) |
| `src/agentml/tools/code_execution.py` | Code execution tools (execute_code, etc.) |
| `src/agentml/tools/dynamic.py` | Dynamic tool creation (create_tool meta-tool) |
| `src/agentml/agents/claude_agent.py` | Claude Agents SDK-powered agent |
| `src/agentml/agents/prompts.py` | System prompt templates |
| `src/agentml/core/agent_run.py` | `AgentRun` and `AgentEvent` domain models |
| `src/agentml/api/routers/agent.py` | Agent run API routes |
| `frontend/src/pages/agent.tsx` | Agent page |
| `frontend/src/hooks/use-agent-runs.ts` | Agent runs SWR hook |
| `frontend/src/hooks/use-agent-events.ts` | SSE event stream hook |
| `frontend/src/components/agent/agent-prompt-form.tsx` | Prompt + tool hints form |
| `frontend/src/components/agent/agent-run-view.tsx` | Live agent run view |
| `frontend/src/components/agent/event-feed.tsx` | Event feed component |
| `tests/unit/test_tool_registry.py` | ToolRegistry unit tests |
| `tests/unit/test_builtin_tools.py` | Built-in tool tests |
| `tests/unit/test_claude_agent.py` | ClaudeAgent tests (mocked API) |
| `tests/e2e/test_agent_run.py` | End-to-end agent run test |

### Modified files

| File | Change |
|---|---|
| `src/agentml/runtime/lab.py` | Add `tool_runtime: ToolRuntime` and `agent: Agent` fields |
| `src/agentml/api/deps.py` | Build `ToolRegistry`, register tools, build agent, wire everything |
| `src/agentml/api/app.py` | Include `agent` router |
| `src/agentml/config/settings.py` | Add `max_agent_turns`, enhance `LLMSettings` |
| `src/agentml/sandbox/local.py` | Persistent workdir, file I/O, venv support |
| `src/agentml/interfaces/sandbox.py` | Add `write_file`, `read_file`, `list_files` optional methods |
| `src/agentml/core/task.py` | Add `ToolHint` dataclass and `tool_hints` field to `Task` |
| `src/agentml/api/routers/tasks.py` | Refactor to use agent from lab instead of hardcoded `StubAgent` |
| `pyproject.toml` | Add `anthropic` dependency, `sse-starlette` for SSE |
| `frontend/src/types.ts` | Add `AgentRun`, `AgentEvent`, `ToolHint` types |
| `frontend/src/App.tsx` | Add agent route |
| `frontend/src/components/layout/shell.tsx` | Add agent nav item |
| `tests/conftest.py` | Update fixtures to include `tool_runtime` and `agent` |

---

## 10. Migration & Sequencing

### Implementation order

```
Phase 1 (Tools foundation)        ~2-3 days
├── 1a. ToolRegistry impl
├── 1b. Schema generation
├── 1c. Built-in tools
├── 1d. Wire into LabEnvironment
└── 1e. Unit tests

Phase 2 (Code execution)          ~1-2 days
├── 2a. Enhanced LocalSandbox
├── 2b. Code execution tools
├── 2c. Sandbox interface expansion
└── 2d. Tests

Phase 3 (Claude agent)            ~2-3 days
├── 3a. ClaudeAgent implementation
├── 3b. System prompt design
├── 3c. Agent selection in config
├── 3d. Agent in LabEnvironment
└── 3e. Tests (mocked Claude API)

Phase 4 (Dynamic tools)           ~1-2 days
├── 4a. ToolHint model + API
├── 4b. create_tool meta-tool
├── 4c. Prompt injection for hints
└── 4d. Tests

Phase 5 (Agent run lifecycle)     ~2-3 days
├── 5a. AgentRun model
├── 5b. Agent run API routes + SSE
├── 5c. Background task execution
├── 5d. Frontend: agent page + components
├── 5e. Frontend: SSE event stream
└── 5f. E2E tests

Phase 6 (Validation)              ~1 day
├── 6a. Boston Housing end-to-end test
├── 6b. Manual validation with real Claude API
└── 6c. Documentation
```

### Breaking changes & backward compatibility

- `LabEnvironment` gains two new required fields (`tool_runtime`, `agent`). All test fixtures must be updated.
- `StubAgent` remains available as fallback when `llm.provider = "stub"`.
- Existing API routes (`/tasks`, `/experiments`, `/knowledge`) are unchanged.
- The `/tasks` POST endpoint should be refactored to use `lab.agent` instead of hardcoded `StubAgent()`.

### Dependencies to add

```toml
# pyproject.toml
dependencies = [
    ...,
    "sse-starlette>=2.0",      # Server-Sent Events for FastAPI
]

[project.optional-dependencies]
anthropic = ["anthropic>=0.80"]  # Already listed
```

### Config defaults (zero-config for stub mode)

```yaml
# .agentml/config.yaml (example for real Claude usage)
llm:
  provider: anthropic
  model: claude-sonnet-4-20250514
  api_key: ${ANTHROPIC_API_KEY}  # or set AGENTML__LLM__API_KEY env var
  max_agent_turns: 50
```

---

## Appendix A: Tool → Claude SDK Format

Each tool registered in `ToolRegistry` must be exportable to:

```json
{
  "name": "create_experiment",
  "description": "Create a new experiment with a hypothesis to test.",
  "input_schema": {
    "type": "object",
    "properties": {
      "task_id": {"type": "string", "description": "The task this experiment belongs to"},
      "hypothesis": {"type": "string", "description": "What you want to test"},
      "variables": {"type": "object", "description": "Variables for the hypothesis"},
      "config": {"type": "object", "description": "Experiment configuration"}
    },
    "required": ["task_id", "hypothesis"]
  }
}
```

## Appendix B: Safety & Limits

| Concern | Mitigation |
|---|---|
| Runaway agent loop | `max_agent_turns` config (default 50) |
| Sandbox code execution | Timeout per execution (configurable, default 30s) |
| Package installation | Allowlist or approval mechanism (future) |
| API cost | Token tracking per run, budget limits (future) |
| Agent stop | `/agent/runs/{id}/stop` endpoint + `asyncio.Event` cancellation |

## Appendix C: Future Enhancements

- **Modal sandbox** — swap `LocalSandbox` for `ModalSandbox` for isolated containerized execution
- **Vector memory** — swap `LocalMemoryStore` for embedding-based semantic search
- **Multi-agent** — multiple specialized agents collaborating (data engineer, ML engineer, evaluator)
- **Human-in-the-loop** — agent pauses for approval at key decision points
- **Experiment templates** — pre-built experiment flows the agent can instantiate
- **Cost tracking** — per-run API + compute cost tracking in the UI
