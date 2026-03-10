# End-to-End Agent Harness v1 — AgentML MCP Tools

> **Goal:** Define all AgentML domain operations as framework-agnostic tool definitions, with an adapter layer that maps them to Claude Agent SDK MCP tools (and later Copilot SDK, raw MCP, etc.).

---

## Key Insight: We Are a Tool Provider, Not an Agent Framework

The Claude Agent SDK (`claude-agent-sdk`) **is** the agent. It already handles:

- The plan → act → observe → repeat loop
- Code execution (built-in `Bash` tool)
- File reading/writing (`Read`, `Write`, `Edit` tools)
- Web fetching (`WebFetch`, `WebSearch` tools)
- Subagent orchestration (`Agent` tool)
- Permission management & sandboxing

**Our job** is to provide well-defined tools that let any agent SDK interact with AgentML's domain — experiments, knowledge, tracking, metrics. The tools themselves are SDK-agnostic; only the adapter layer knows about a specific SDK.

```
┌──────────────────────────────────────────────────────────────┐
│                  Agent SDK (Claude / Copilot / …)            │
│  Built-in: Bash, Read, Write, Edit, WebFetch…               │
│                                                              │
│  + AgentML Tools (via adapter)                               │
│    ├── create_experiment                                     │
│    ├── complete_experiment                                   │
│    ├── fail_experiment                                       │
│    ├── log_metrics                                           │
│    ├── log_params                                            │
│    ├── list_experiments                                      │
│    ├── get_experiment                                        │
│    ├── compare_experiments                                   │
│    ├── write_knowledge                                       │
│    ├── search_knowledge                                      │
│    └── list_knowledge                                        │
│                                                              │
│  Adapter layer (ports & adapters)                            │
│    ├── ClaudeToolAdapter  → @tool + create_sdk_mcp_server()  │
│    ├── (future) CopilotToolAdapter → Copilot SDK format      │
│    └── (future) MCPToolAdapter → raw MCP protocol            │
│                                                              │
│  ToolDef (framework-agnostic)                                │
│    name, description, parameters (JSON Schema), handler(fn)  │
│                                                              │
│  Backed by: LabEnvironment                                   │
│    ├── experiment_store (LocalExperimentStore)                │
│    ├── memory_store (LocalMemoryStore)                        │
│    ├── tracking (FileTracker / MlflowTracker)                │
│    ├── artifact_store (LocalArtifactStore)                    │
│    └── sandbox (LocalSandbox) — for future use               │
└──────────────────────────────────────────────────────────────┘
```

---

## Table of Contents

1. [What We Build in v1](#1-what-we-build-in-v1)
2. [Tool Abstraction Layer](#2-tool-abstraction-layer)
3. [Tool Definitions](#3-tool-definitions)
4. [Adapter Layer](#4-adapter-layer)
5. [MCP Server Factory](#5-mcp-server-factory)
6. [LabEnvironment Changes](#6-labenvironment-changes)
7. [Standalone Test Script](#7-standalone-test-script)
8. [File-by-File Change Map](#8-file-by-file-change-map)
9. [Implementation Steps](#9-implementation-steps)
10. [What We Do NOT Build in v1](#10-what-we-do-not-build-in-v1)

---

## 1. What We Build in v1

| Deliverable | Description |
|---|---|
| **`ToolDef` abstraction** | Framework-agnostic dataclass: `name`, `description`, `parameters` (JSON Schema), `handler` (async callable) |
| **`ToolResult` abstraction** | Standard return type wrapping tool output, errors, and metadata |
| **AgentML tool definitions** | 11 tools defined as `ToolDef` instances, each backed by `LabEnvironment` services |
| **`ClaudeToolAdapter`** | Adapter that converts `ToolDef` → Claude Agent SDK `@tool` decorated functions |
| **MCP server factory** | `create_agentml_server(lab)` → uses adapter to produce `McpSdkServerConfig` |
| **Tool unit tests** | Each tool handler tested in isolation (no SDK dependency needed) |
| **Standalone validation script** | A script that wires tools through the Claude adapter and runs a simple experiment |
| **Dependency addition** | `claude-agent-sdk` added to `pyproject.toml` optional deps |

### What we explicitly do NOT build

- No new API routes (that's v2)
- No frontend changes (that's v2)
- No custom agent loop (Claude Code IS the agent)
- No custom code sandbox for the agent (Claude Code has `Bash`)
- No Copilot/MCP adapters yet (just the interface + Claude impl)

---

## 2. Tool Abstraction Layer

The abstraction sits between our domain tools and any SDK. Tools define *what* they do; adapters define *how* they're exposed.

### 2.1 `ToolDef` — Framework-Agnostic Tool Definition

**File:** `src/agentml/tools/base.py`

```python
# src/agentml/tools/base.py
"""Framework-agnostic tool definitions for AgentML."""

from __future__ import annotations

import json
from collections.abc import Callable, Awaitable
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ToolResult:
    """Standard return type for all tool handlers.

    Framework adapters convert this to their SDK-specific format
    (e.g. Claude's {"content": [{"type": "text", "text": "..."}]}).
    """

    data: Any = None
    error: str | None = None

    @property
    def is_error(self) -> bool:
        return self.error is not None

    def to_text(self) -> str:
        """Serialize to JSON text for agent consumption."""
        if self.error:
            return json.dumps({"error": self.error}, default=str)
        return json.dumps(self.data, default=str)


# Type alias for tool handler functions
ToolHandler = Callable[[dict[str, Any]], Awaitable[ToolResult]]


@dataclass(frozen=True)
class ToolDef:
    """A framework-agnostic tool definition.

    This is the core abstraction. Each tool is defined once as a ToolDef,
    then mapped to any agent SDK via an adapter.

    Args:
        name: Unique tool name (e.g. "create_experiment")
        description: What the tool does — shown to the agent as context
        parameters: JSON Schema describing the tool's input
        handler: Async function (dict → ToolResult) implementing the tool
    """

    name: str
    description: str
    parameters: dict[str, Any]
    handler: ToolHandler


@dataclass
class ToolRegistry:
    """A simple collection of ToolDef instances.

    Not tied to any SDK — just a way to group tools for passing to an adapter.
    """

    _tools: list[ToolDef] = field(default_factory=list)

    def register(self, tool: ToolDef) -> None:
        self._tools.append(tool)

    def register_all(self, tools: list[ToolDef]) -> None:
        self._tools.extend(tools)

    @property
    def tools(self) -> list[ToolDef]:
        return list(self._tools)

    @property
    def tool_names(self) -> list[str]:
        return [t.name for t in self._tools]
```

### 2.2 Why This Design

| Concern | How it's handled |
|---|---|
| **SDK independence** | Tool handlers return `ToolResult`, not `{"content": [...]}`. The adapter does the format conversion. |
| **Testability** | Tests call `handler(args)` directly — no SDK imports needed. Assert on `ToolResult.data` / `.error`. |
| **Swappability** | To switch from Claude to Copilot: change one line (which adapter to use). All tool definitions stay the same. |
| **Schema reuse** | `parameters` is JSON Schema — the universal standard. Every SDK understands it or can trivially convert. |
| **Type safety** | `ToolDef` is a frozen dataclass. `ToolHandler` is a proper type alias. |

### 2.3 Replaces `ToolRuntime` Interface

The existing `ToolRuntime` ABC (`src/agentml/interfaces/tool_runtime.py`) defined `register_tool()`, `list_tools()`, `call_tool()` — a register-and-dispatch pattern tightly coupled to a single runtime. 

The new pattern is:
- **`ToolDef`** replaces `register_tool()` — tools are data, not registered callbacks
- **`ToolRegistry`** replaces `list_tools()` — a simple list, no runtime coupling
- **The agent SDK** replaces `call_tool()` — the SDK dispatches tool calls, not us

**Action:** Delete `src/agentml/interfaces/tool_runtime.py` and remove its re-export from `interfaces/__init__.py`.

---

## 3. Tool Definitions

All tools live in `src/agentml/tools/`. Each tool module exports a function `create_*_tools(lab) → list[ToolDef]` that returns framework-agnostic tool definitions.

### 3.1 Experiment Tools

**File:** `src/agentml/tools/experiments.py`

| Tool | Args | Description | Delegates to |
|---|---|---|---|
| `create_experiment` | `task_id: str`, `hypothesis: str`, `variables?: dict`, `config?: dict` | Create a new experiment with a hypothesis | `ExperimentService.create()` |
| `complete_experiment` | `experiment_id: str`, `metrics?: dict`, `logs?: list[str]` | Mark experiment as completed with results | `ExperimentService.complete()` |
| `fail_experiment` | `experiment_id: str`, `error: str` | Mark experiment as failed | `ExperimentService.fail()` |
| `get_experiment` | `experiment_id: str` | Get experiment details | `ExperimentService.get()` |
| `list_experiments` | `task_id?: str` | List experiments, optionally filtered | `ExperimentService.list()` |
| `compare_experiments` | `experiment_ids: list[str]` | Compare metrics across experiments | Multiple `ExperimentService.get()` + format |

```python
# src/agentml/tools/experiments.py
"""AgentML experiment management tools."""

from typing import Any

from agentml.core.experiment import Experiment, ExperimentResult, Hypothesis
from agentml.runtime.experiment_service import ExperimentService
from agentml.runtime.lab import LabEnvironment
from agentml.tools.base import ToolDef, ToolResult


def create_experiment_tools(lab: LabEnvironment) -> list[ToolDef]:
    """Create all experiment tools backed by a LabEnvironment."""
    service = ExperimentService(lab)

    async def create_experiment(args: dict[str, Any]) -> ToolResult:
        exp = Experiment(
            task_id=args["task_id"],
            hypothesis=Hypothesis(
                description=args["hypothesis"],
                variables=args.get("variables", {}),
            ),
            config=args.get("config", {}),
        )
        exp_id = await service.create(exp)
        await service.run(exp_id)
        return ToolResult(data={"experiment_id": exp_id, "status": "running"})

    async def complete_experiment(args: dict[str, Any]) -> ToolResult:
        exp = await service.get(args["experiment_id"])
        if exp is None:
            return ToolResult(error=f"Experiment {args['experiment_id']} not found")
        exp.result = ExperimentResult(
            metrics=args.get("metrics", {}),
            logs=args.get("logs", []),
        )
        await service.complete(exp)
        return ToolResult(data={
            "experiment_id": exp.id,
            "status": "completed",
            "metrics": exp.result.metrics,
        })

    async def fail_experiment(args: dict[str, Any]) -> ToolResult:
        exp = await service.get(args["experiment_id"])
        if exp is None:
            return ToolResult(error=f"Experiment {args['experiment_id']} not found")
        await service.fail(exp, args["error"])
        return ToolResult(data={"experiment_id": exp.id, "status": "failed"})

    async def get_experiment(args: dict[str, Any]) -> ToolResult:
        exp = await service.get(args["experiment_id"])
        if exp is None:
            return ToolResult(error="Not found")
        return ToolResult(data={
            "id": exp.id,
            "task_id": exp.task_id,
            "state": exp.state.value,
            "hypothesis": exp.hypothesis.description if exp.hypothesis else None,
            "variables": exp.hypothesis.variables if exp.hypothesis else {},
            "config": exp.config,
            "metrics": exp.result.metrics if exp.result else None,
            "logs": exp.result.logs if exp.result else [],
            "error": exp.result.error if exp.result else None,
        })

    async def list_experiments(args: dict[str, Any]) -> ToolResult:
        experiments = await service.list(task_id=args.get("task_id"))
        return ToolResult(data=[
            {
                "id": e.id,
                "state": e.state.value,
                "hypothesis": e.hypothesis.description if e.hypothesis else None,
                "metrics": e.result.metrics if e.result else None,
            }
            for e in experiments
        ])

    async def compare_experiments(args: dict[str, Any]) -> ToolResult:
        rows = []
        for eid in args["experiment_ids"]:
            exp = await service.get(eid)
            if exp:
                rows.append({
                    "id": exp.id,
                    "hypothesis": exp.hypothesis.description if exp.hypothesis else "—",
                    "state": exp.state.value,
                    "metrics": exp.result.metrics if exp.result else {},
                    "config": exp.config,
                })
        return ToolResult(data={"comparison": rows, "count": len(rows)})

    return [
        ToolDef(
            name="create_experiment",
            description=(
                "Create a new ML experiment with a hypothesis to test. Returns the experiment ID. "
                "Always create an experiment before running code for it."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "The task this experiment belongs to"},
                    "hypothesis": {"type": "string", "description": "What you want to test or prove"},
                    "variables": {
                        "type": "object",
                        "description": "Key variables for the hypothesis (e.g. model type, hyperparams)",
                    },
                    "config": {
                        "type": "object",
                        "description": "Experiment configuration metadata",
                    },
                },
                "required": ["task_id", "hypothesis"],
            },
            handler=create_experiment,
        ),
        ToolDef(
            name="complete_experiment",
            description=(
                "Mark an experiment as completed with its metrics and optional logs. "
                "Call this after your code has run and you have results."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "experiment_id": {"type": "string"},
                    "metrics": {
                        "type": "object",
                        "description": "Metric name → float value (e.g. {'rmse': 4.2, 'r2': 0.87})",
                    },
                    "logs": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional log messages",
                    },
                },
                "required": ["experiment_id"],
            },
            handler=complete_experiment,
        ),
        ToolDef(
            name="fail_experiment",
            description="Mark an experiment as failed with an error message.",
            parameters={
                "type": "object",
                "properties": {
                    "experiment_id": {"type": "string"},
                    "error": {"type": "string", "description": "What went wrong"},
                },
                "required": ["experiment_id", "error"],
            },
            handler=fail_experiment,
        ),
        ToolDef(
            name="get_experiment",
            description="Get full details of an experiment including its state, hypothesis, config, and results.",
            parameters={
                "type": "object",
                "properties": {
                    "experiment_id": {"type": "string", "description": "The experiment ID"},
                },
                "required": ["experiment_id"],
            },
            handler=get_experiment,
        ),
        ToolDef(
            name="list_experiments",
            description="List all experiments, optionally filtered by task ID.",
            parameters={
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "Filter by task ID (optional)"},
                },
            },
            handler=list_experiments,
        ),
        ToolDef(
            name="compare_experiments",
            description=(
                "Compare metrics across multiple experiments side by side. "
                "Use this to evaluate which approach works best."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "experiment_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of experiment IDs to compare",
                    },
                },
                "required": ["experiment_ids"],
            },
            handler=compare_experiments,
        ),
    ]
```

### 3.2 Knowledge Tools

**File:** `src/agentml/tools/knowledge.py`

| Tool | Args | Description | Delegates to |
|---|---|---|---|
| `write_knowledge` | `context`, `claim`, `action?`, `confidence?`, `evidence_ids?` | Record a learning as a knowledge atom | `MemoryStore.add()` |
| `search_knowledge` | `query`, `limit?` | Search for relevant prior learnings | `MemoryStore.search()` |
| `list_knowledge` | — | List all knowledge atoms | `MemoryStore.list()` |

```python
# src/agentml/tools/knowledge.py
"""AgentML knowledge management tools."""

from typing import Any

from agentml.core.knowledge import KnowledgeAtom
from agentml.runtime.lab import LabEnvironment
from agentml.tools.base import ToolDef, ToolResult


def create_knowledge_tools(lab: LabEnvironment) -> list[ToolDef]:
    """Create all knowledge tools backed by a LabEnvironment."""

    async def write_knowledge(args: dict[str, Any]) -> ToolResult:
        atom = KnowledgeAtom(
            context=args["context"],
            claim=args["claim"],
            action=args.get("action", ""),
            confidence=args.get("confidence", 0.0),
            evidence_ids=args.get("evidence_ids", []),
        )
        atom_id = await lab.memory_store.add(atom)
        return ToolResult(data={"atom_id": atom_id, "status": "saved"})

    async def search_knowledge(args: dict[str, Any]) -> ToolResult:
        atoms = await lab.memory_store.search(
            args["query"], limit=args.get("limit", 10)
        )
        return ToolResult(data=[
            {
                "id": a.id,
                "context": a.context,
                "claim": a.claim,
                "action": a.action,
                "confidence": a.confidence,
                "evidence_ids": a.evidence_ids,
            }
            for a in atoms
        ])

    async def list_knowledge(args: dict[str, Any]) -> ToolResult:
        atoms = await lab.memory_store.list()
        return ToolResult(data=[
            {
                "id": a.id,
                "context": a.context,
                "claim": a.claim,
                "action": a.action,
                "confidence": a.confidence,
            }
            for a in atoms
        ])

    return [
        ToolDef(
            name="write_knowledge",
            description=(
                "Record a learning or insight from your experiments as a knowledge atom. "
                "Do this whenever you discover something meaningful — model comparisons, "
                "feature importance findings, hyperparameter effects, etc."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "context": {"type": "string", "description": "What situation/experiment this learning comes from"},
                    "claim": {"type": "string", "description": "The factual claim or finding"},
                    "action": {"type": "string", "description": "Recommended action based on this finding"},
                    "confidence": {"type": "number", "description": "Confidence 0.0–1.0"},
                    "evidence_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Experiment IDs that support this claim",
                    },
                },
                "required": ["context", "claim"],
            },
            handler=write_knowledge,
        ),
        ToolDef(
            name="search_knowledge",
            description=(
                "Search for previously recorded knowledge atoms relevant to a query. "
                "Use this to recall prior learnings before starting a new experiment."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "What to search for"},
                    "limit": {"type": "integer", "description": "Max results (default 10)"},
                },
                "required": ["query"],
            },
            handler=search_knowledge,
        ),
        ToolDef(
            name="list_knowledge",
            description="List all recorded knowledge atoms.",
            parameters={"type": "object", "properties": {}},
            handler=list_knowledge,
        ),
    ]
```

### 3.3 Tracking Tools

**File:** `src/agentml/tools/tracking.py`

| Tool | Args | Description | Delegates to |
|---|---|---|---|
| `log_metrics` | `experiment_id`, `metrics` | Log metrics to tracking backend | `TrackingConnector.log_metrics()` |
| `log_params` | `experiment_id`, `params` | Log parameters to tracking backend | `TrackingConnector.log_params()` |

```python
# src/agentml/tools/tracking.py
"""AgentML tracking tools."""

from typing import Any

from agentml.runtime.lab import LabEnvironment
from agentml.tools.base import ToolDef, ToolResult


def create_tracking_tools(lab: LabEnvironment) -> list[ToolDef]:
    """Create tracking tools backed by a LabEnvironment."""

    async def log_metrics(args: dict[str, Any]) -> ToolResult:
        await lab.tracking.log_metrics(args["experiment_id"], args["metrics"])
        return ToolResult(data={"status": "logged", "experiment_id": args["experiment_id"]})

    async def log_params(args: dict[str, Any]) -> ToolResult:
        await lab.tracking.log_params(args["experiment_id"], args["params"])
        return ToolResult(data={"status": "logged", "experiment_id": args["experiment_id"]})

    return [
        ToolDef(
            name="log_metrics",
            description=(
                "Log numeric metrics for an experiment to the tracking backend (MLflow or file). "
                "Call this after evaluating a model."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "experiment_id": {"type": "string"},
                    "metrics": {
                        "type": "object",
                        "description": "Metric name → float value (e.g. {'accuracy': 0.95})",
                    },
                },
                "required": ["experiment_id", "metrics"],
            },
            handler=log_metrics,
        ),
        ToolDef(
            name="log_params",
            description="Log parameters/hyperparameters for an experiment to the tracking backend.",
            parameters={
                "type": "object",
                "properties": {
                    "experiment_id": {"type": "string"},
                    "params": {
                        "type": "object",
                        "description": "Parameter name → value (e.g. {'learning_rate': 0.01})",
                    },
                },
                "required": ["experiment_id", "params"],
            },
            handler=log_params,
        ),
    ]
```

---

## 4. Adapter Layer

Adapters convert `ToolDef` instances into SDK-specific tool objects. Each adapter implements the same interface pattern.

### 4.1 Adapter ABC

**File:** `src/agentml/tools/adapters/base.py`

```python
# src/agentml/tools/adapters/base.py
"""Base adapter interface for converting ToolDef to SDK-specific formats."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from agentml.tools.base import ToolDef


class ToolAdapter(ABC):
    """Abstract adapter: converts ToolDef instances to SDK-specific tool objects.

    Each concrete adapter knows how to:
    1. Convert a ToolDef → SDK tool object (adapt_tool)
    2. Bundle multiple tools into a server/config (create_server)
    """

    @abstractmethod
    def adapt_tool(self, tool_def: ToolDef) -> Any:
        """Convert a single ToolDef to an SDK-specific tool object.

        Args:
            tool_def: The framework-agnostic tool definition.

        Returns:
            An SDK-specific tool object (e.g. Claude's SdkMcpTool).
        """
        ...

    def adapt_all(self, tool_defs: list[ToolDef]) -> list[Any]:
        """Convert multiple ToolDefs. Default: map adapt_tool over each."""
        return [self.adapt_tool(td) for td in tool_defs]

    @abstractmethod
    def create_server(
        self,
        name: str,
        tool_defs: list[ToolDef],
        *,
        version: str = "0.1.0",
    ) -> Any:
        """Bundle tools into an SDK-specific server configuration.

        Args:
            name: Server name identifier.
            tool_defs: Tools to include in the server.
            version: Server version string.

        Returns:
            SDK-specific server config object.
        """
        ...

    def tool_names_prefixed(self, server_name: str, tool_defs: list[ToolDef]) -> list[str]:
        """Return the SDK-prefixed tool names for an allowed_tools list.

        Default implementation returns plain names. Override for SDKs
        that use prefixes (e.g. Claude's "mcp__server__tool" pattern).
        """
        return [td.name for td in tool_defs]
```

### 4.2 Claude Agent SDK Adapter

**File:** `src/agentml/tools/adapters/claude.py`

```python
# src/agentml/tools/adapters/claude.py
"""Claude Agent SDK adapter — converts ToolDef to @tool decorated functions."""

from __future__ import annotations

from typing import Any

from claude_agent_sdk import tool as sdk_tool, create_sdk_mcp_server

from agentml.tools.base import ToolDef, ToolResult


class ClaudeToolAdapter:
    """Converts ToolDef instances to Claude Agent SDK MCP tools.

    The Claude SDK expects tools decorated with @tool that return:
        {"content": [{"type": "text", "text": "..."}]}

    This adapter wraps our ToolDef handlers to produce that format.
    """

    def _to_claude_response(self, result: ToolResult) -> dict[str, Any]:
        """Convert a ToolResult to Claude's expected response format."""
        return {"content": [{"type": "text", "text": result.to_text()}]}

    def adapt_tool(self, tool_def: ToolDef) -> Any:
        """Convert a ToolDef to a Claude @tool decorated function."""
        adapter = self

        @sdk_tool(tool_def.name, tool_def.description, tool_def.parameters)
        async def wrapped(args: dict[str, Any]) -> dict[str, Any]:
            result = await tool_def.handler(args)
            return adapter._to_claude_response(result)

        return wrapped

    def adapt_all(self, tool_defs: list[ToolDef]) -> list[Any]:
        return [self.adapt_tool(td) for td in tool_defs]

    def create_server(
        self,
        name: str,
        tool_defs: list[ToolDef],
        *,
        version: str = "0.1.0",
    ) -> Any:
        """Bundle tools into a Claude MCP server config.

        Returns:
            McpSdkServerConfig ready for ClaudeAgentOptions.mcp_servers.
        """
        sdk_tools = self.adapt_all(tool_defs)
        return create_sdk_mcp_server(
            name=name,
            version=version,
            tools=sdk_tools,
        )

    def tool_names_prefixed(self, server_name: str, tool_defs: list[ToolDef]) -> list[str]:
        """Return Claude's prefixed tool names: mcp__<server>__<tool>."""
        return [f"mcp__{server_name}__{td.name}" for td in tool_defs]
```

### 4.3 How It Works Together

```python
# Example: wiring it all up
from agentml.tools.experiments import create_experiment_tools
from agentml.tools.knowledge import create_knowledge_tools
from agentml.tools.tracking import create_tracking_tools
from agentml.tools.adapters.claude import ClaudeToolAdapter

# 1. Create framework-agnostic tool definitions
all_tools = [
    *create_experiment_tools(lab),
    *create_knowledge_tools(lab),
    *create_tracking_tools(lab),
]

# 2. Adapt to Claude SDK format
adapter = ClaudeToolAdapter()
server = adapter.create_server("agentml", all_tools)
allowed = adapter.tool_names_prefixed("agentml", all_tools)

# 3. Use with Claude
options = ClaudeAgentOptions(
    mcp_servers={"agentml": server},
    allowed_tools=allowed,
)
```

### 4.4 Future Adapters (sketch, not built in v1)

```python
# Copilot SDK adapter (future)
class CopilotToolAdapter(ToolAdapter):
    def adapt_tool(self, tool_def: ToolDef) -> Any:
        # Convert to Copilot's tool format
        return CopilotTool(
            name=tool_def.name,
            description=tool_def.description,
            input_schema=tool_def.parameters,
            handler=lambda args: tool_def.handler(args),
        )

# Raw MCP adapter (future)
class MCPToolAdapter(ToolAdapter):
    def adapt_tool(self, tool_def: ToolDef) -> Any:
        # Convert to standard MCP tool descriptor
        return {
            "name": tool_def.name,
            "description": tool_def.description,
            "inputSchema": tool_def.parameters,
        }
```

---

## 5. MCP Server Factory

**File:** `src/agentml/tools/server.py`

This is the composition root for all AgentML tools. It collects all tool definitions and uses the appropriate adapter.

```python
# src/agentml/tools/server.py
"""AgentML tool server — bundles all tools and adapts to target SDK."""

from __future__ import annotations

from typing import Any

from agentml.runtime.lab import LabEnvironment
from agentml.tools.base import ToolDef, ToolRegistry
from agentml.tools.experiments import create_experiment_tools
from agentml.tools.knowledge import create_knowledge_tools
from agentml.tools.tracking import create_tracking_tools


def collect_all_tools(lab: LabEnvironment) -> list[ToolDef]:
    """Collect all AgentML tool definitions backed by a LabEnvironment.

    Returns framework-agnostic ToolDef instances — not tied to any SDK.
    """
    return [
        *create_experiment_tools(lab),
        *create_knowledge_tools(lab),
        *create_tracking_tools(lab),
    ]


def create_agentml_server(lab: LabEnvironment, *, adapter: str = "claude") -> Any:
    """Create the AgentML tool server using the specified adapter.

    Args:
        lab: The LabEnvironment providing all backend services.
        adapter: Which SDK adapter to use ("claude" for now).

    Returns:
        SDK-specific server config (e.g. McpSdkServerConfig for Claude).
    """
    tools = collect_all_tools(lab)

    if adapter == "claude":
        from agentml.tools.adapters.claude import ClaudeToolAdapter

        return ClaudeToolAdapter().create_server("agentml", tools)
    else:
        msg = f"Unknown tool adapter: {adapter}"
        raise ValueError(msg)


def get_allowed_tool_names(
    lab: LabEnvironment,
    server_name: str = "agentml",
    *,
    adapter: str = "claude",
) -> list[str]:
    """Get the SDK-prefixed tool names for allowed_tools configuration.

    Args:
        lab: The LabEnvironment.
        server_name: The MCP server name.
        adapter: Which SDK adapter to use.

    Returns:
        List of prefixed tool names (e.g. ["mcp__agentml__create_experiment", ...]).
    """
    tools = collect_all_tools(lab)

    if adapter == "claude":
        from agentml.tools.adapters.claude import ClaudeToolAdapter

        return ClaudeToolAdapter().tool_names_prefixed(server_name, tools)
    else:
        return [t.name for t in tools]
```

Usage (preview of v2, but useful for standalone testing now):

```python
from claude_agent_sdk import query, ClaudeAgentOptions
from agentml.api.deps import build_lab
from agentml.config.settings import Settings
from agentml.tools.server import create_agentml_server, get_allowed_tool_names

settings = Settings.load()
lab = build_lab(settings)

server = create_agentml_server(lab)
allowed = get_allowed_tool_names(lab)

options = ClaudeAgentOptions(
    mcp_servers={"agentml": server},
    allowed_tools=[*allowed, "Bash", "Read", "Write"],
    permission_mode="acceptEdits",
    max_turns=50,
)

async for message in query(prompt="...", options=options):
    print(message)
```

---

## 6. LabEnvironment Changes

### Minimal — no structural changes needed for v1

The `LabEnvironment` dataclass stays the same. Our tools receive `lab` via closure in the factory functions, not through the DI container. This means:

- **No** new fields on `LabEnvironment`
- **No** changes to `build_lab()`
- **No** changes to existing tests

The only change is the new `src/agentml/tools/` package that imports from existing modules.

### Clean up `ToolRuntime` interface

Since the `ToolDef` + adapter pattern supersedes `ToolRuntime`:

1. Delete `src/agentml/interfaces/tool_runtime.py`
2. Remove `ToolRuntime` from `src/agentml/interfaces/__init__.py` (if re-exported)

---

## 7. Standalone Test Script

**File:** `scripts/test_tools_standalone.py`

A script to validate the tools work end-to-end with a real Claude Code session.

```python
#!/usr/bin/env python3
"""Standalone test: run a simple ML task with AgentML tools via Claude Agent SDK."""

import asyncio

from claude_agent_sdk import (
    ClaudeAgentOptions,
    AssistantMessage,
    ResultMessage,
    TextBlock,
    ToolUseBlock,
    query,
)

from agentml.api.deps import build_lab
from agentml.config.settings import Settings
from agentml.tools.server import create_agentml_server, get_allowed_tool_names
from agentml.utils.ids import generate_id


async def main():
    # Build lab with default settings (file-based storage in .agentml/)
    settings = Settings.load()
    lab = build_lab(settings)

    # Create our MCP server via the Claude adapter
    server = create_agentml_server(lab)  # defaults to adapter="claude"
    allowed = get_allowed_tool_names(lab)

    task_id = generate_id()

    options = ClaudeAgentOptions(
        mcp_servers={"agentml": server},
        allowed_tools=[
            *allowed,          # All AgentML tools
            "Bash",            # Claude Code built-ins
            "Read",
            "Write",
        ],
        permission_mode="acceptEdits",
        max_turns=30,
    )

    prompt = f"""You are an ML research agent. Your task ID is: {task_id}

Task: Train a simple linear regression on the California Housing dataset and evaluate it.

Steps:
1. Use create_experiment to register what you're doing
2. Write and run Python code (using Bash) to train the model
3. Log the metrics with log_metrics and complete_experiment
4. Write a knowledge atom about what you learned

Use scikit-learn. Keep it simple — this is a validation test."""

    print(f"Starting agent run (task_id={task_id})...\n")

    async for message in query(prompt=prompt, options=options):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    print(f"[Claude] {block.text[:200]}")
                elif isinstance(block, ToolUseBlock):
                    print(f"[Tool] {block.name}({list(block.input.keys())})")
        elif isinstance(message, ResultMessage):
            print(f"\n--- Done in {message.duration_ms}ms, {message.num_turns} turns ---")
            if message.total_cost_usd:
                print(f"Cost: ${message.total_cost_usd:.4f}")

    # Verify results persisted
    experiments = await lab.experiment_store.list(task_id=task_id)
    print(f"\nExperiments stored: {len(experiments)}")
    for exp in experiments:
        print(f"  {exp.id}: {exp.state.value} — {exp.result.metrics if exp.result else '—'}")

    knowledge = await lab.memory_store.list()
    print(f"Knowledge atoms: {len(knowledge)}")
    for atom in knowledge:
        print(f"  {atom.claim[:80]}")


if __name__ == "__main__":
    asyncio.run(main())
```

---

## 8. File-by-File Change Map

### New files

| File | Purpose |
|---|---|
| `src/agentml/tools/__init__.py` | Package init — re-exports `ToolDef`, `ToolResult`, `ToolRegistry` |
| `src/agentml/tools/base.py` | `ToolDef`, `ToolResult`, `ToolHandler`, `ToolRegistry` — the abstraction |
| `src/agentml/tools/experiments.py` | Experiment tool definitions (6 `ToolDef`s) |
| `src/agentml/tools/knowledge.py` | Knowledge tool definitions (3 `ToolDef`s) |
| `src/agentml/tools/tracking.py` | Tracking tool definitions (2 `ToolDef`s) |
| `src/agentml/tools/server.py` | `collect_all_tools()`, `create_agentml_server()`, `get_allowed_tool_names()` |
| `src/agentml/tools/adapters/__init__.py` | Adapters package init |
| `src/agentml/tools/adapters/base.py` | `ToolAdapter` ABC |
| `src/agentml/tools/adapters/claude.py` | `ClaudeToolAdapter` — Claude Agent SDK adapter |
| `scripts/test_tools_standalone.py` | Standalone validation script |
| `tests/unit/test_tool_base.py` | Unit tests for `ToolDef`, `ToolResult`, `ToolRegistry` |
| `tests/unit/test_experiment_tools.py` | Unit tests for experiment tool handlers |
| `tests/unit/test_knowledge_tools.py` | Unit tests for knowledge tool handlers |
| `tests/unit/test_tracking_tools.py` | Unit tests for tracking tool handlers |
| `tests/unit/test_claude_adapter.py` | Unit tests for `ClaudeToolAdapter` |

### Modified files

| File | Change |
|---|---|
| `pyproject.toml` | Add `claude-agent-sdk` to optional deps (e.g. `agent` extra) |

### Deleted files

| File | Reason |
|---|---|
| `src/agentml/interfaces/tool_runtime.py` | Superseded by `ToolDef` + adapter pattern |

### Unchanged

Everything else — `LabEnvironment`, `build_lab()`, `ExperimentService`, API routes, frontend, existing tests. Zero breaking changes.

---

## 9. Implementation Steps

```
Step 1 — Dependency setup                     ~15 min
├── Add claude-agent-sdk to pyproject.toml (optional "agent" extra)
├── uv sync --all-extras
└── Verify import: python -c "from claude_agent_sdk import tool"

Step 2 — Tool abstraction layer               ~30 min
├── Create src/agentml/tools/__init__.py
├── Create src/agentml/tools/base.py (ToolDef, ToolResult, ToolRegistry)
├── Unit test ToolResult.to_text(), ToolRegistry.register()
└── Delete src/agentml/interfaces/tool_runtime.py

Step 3 — Adapter layer                        ~30 min
├── Create src/agentml/tools/adapters/__init__.py
├── Create src/agentml/tools/adapters/base.py (ToolAdapter ABC)
├── Create src/agentml/tools/adapters/claude.py (ClaudeToolAdapter)
└── Unit test adapter: ToolDef → Claude format round-trip

Step 4 — Experiment tools                     ~45 min
├── Create src/agentml/tools/experiments.py
├── 6 tools: create, complete, fail, get, list, compare
└── Unit test each handler (returns ToolResult, no SDK deps)

Step 5 — Knowledge tools                      ~30 min
├── Create src/agentml/tools/knowledge.py
├── 3 tools: write, search, list
└── Unit tests

Step 6 — Tracking tools                       ~20 min
├── Create src/agentml/tools/tracking.py
├── 2 tools: log_metrics, log_params
└── Unit tests

Step 7 — Server factory                       ~15 min
├── Create src/agentml/tools/server.py
├── collect_all_tools(), create_agentml_server(), get_allowed_tool_names()
└── Verify all 11 tools collected

Step 8 — Standalone validation                ~30 min
├── Create scripts/test_tools_standalone.py
├── Run with real Claude Code CLI
└── Verify: experiment created, code ran, metrics logged, knowledge saved

Step 9 — Run existing tests (regression)      ~10 min
└── make test — ensure nothing broke
```

**Total estimated time: ~3.5-4 hours**

---

## 10. What We Do NOT Build in v1

These are explicitly deferred to v2:

| Item | Why deferred |
|---|---|
| Copilot / MCP adapters | v1 ships Claude adapter only; interface is ready for extension |
| API routes for agent runs | Need the full harness first (v2) |
| Frontend agent page | Depends on API routes (v2) |
| SSE event streaming | Depends on agent run lifecycle (v2) |
| Dynamic tool creation (`create_tool`) | Nice-to-have, not needed for MVP (v2+) |
| Task-level tool hints | Depends on agent run API (v2) |
| `ClaudeSDKClient` session management | v2 — for long-running agent sessions |
| Hooks for event capture | v2 — for UI event streaming |
| Agent permission handling | v2 — custom `can_use_tool` callback |
| Sandbox configuration | v2 — Claude Code's built-in sandbox is sufficient for now |

---

## Testing Strategy

### Testing tool handlers (SDK-free)

Tool handlers are just async functions returning `ToolResult`. Tests call them directly — no SDK import needed:

```python
# tests/unit/test_experiment_tools.py
import json
import pytest
from agentml.tools.experiments import create_experiment_tools
from agentml.tools.base import ToolResult


async def test_create_and_complete_experiment(lab):
    tools = create_experiment_tools(lab)
    create_tool = next(t for t in tools if t.name == "create_experiment")

    # Call handler directly — no SDK involved
    result = await create_tool.handler({
        "task_id": "test-task",
        "hypothesis": "Test hypothesis",
    })

    assert isinstance(result, ToolResult)
    assert not result.is_error
    assert "experiment_id" in result.data
    assert result.data["status"] == "running"
```

### Testing the adapter (SDK-dependent but lightweight)

```python
# tests/unit/test_claude_adapter.py
from agentml.tools.base import ToolDef, ToolResult
from agentml.tools.adapters.claude import ClaudeToolAdapter


async def test_claude_adapter_wraps_handler():
    async def my_handler(args):
        return ToolResult(data={"greeting": f"Hello, {args['name']}!"})

    tool_def = ToolDef(
        name="greet",
        description="Greet a user",
        parameters={
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        },
        handler=my_handler,
    )

    adapter = ClaudeToolAdapter()
    sdk_tool = adapter.adapt_tool(tool_def)

    # The wrapped function should return Claude's format
    result = await sdk_tool({"name": "Alice"})
    assert result["content"][0]["type"] == "text"
    assert "Hello, Alice!" in result["content"][0]["text"]
```

This keeps tests fast, isolated, and independent of Claude Code CLI availability. The adapter test is the only one that imports `claude_agent_sdk`.
