# MASTER_PLAN.md — Dojo.ml Vision & Architecture

> **Dojo.ml** — An autonomous ML research framework. Define a research domain with a frozen data + evaluation contract, and an agent runs experiments against it overnight, accumulating compressed knowledge of what actually works.

---

## 1. Vision

### What we're building

Dojo runs **controlled, reproducible ML experiments on your existing pipelines and builds a memory of what actually works.** A human defines a *domain* — a research area pointing at real data with a fixed evaluation contract — and an autonomous agent iterates on training code inside that contract, learning across many experiments.

The structural insight: the framework, not the agent, owns evaluation. Agents are creative but unreliable; their reports of their own performance are not. So we draw a hard line:

```
prepare.py        → load_data tool + evaluate tool          (frozen — framework + human + AI at setup)
train.py          → run_experiment_code per experiment      (mutable — agent edits)
program.md        → Domain.prompt (steering prompt)         (human edits between runs)
```

This is the [Karpathy autoresearch](https://github.com/karpathy/autoresearch) split — `prepare.py` is fixed, `train.py` is fair game, `program.md` is what the human iterates on. We're generalising that pattern beyond LLM training so it works for any well-defined ML problem class — starting with regression.

### Why a framework, not a script

Anyone can wire Claude up to a Jupyter notebook for an evening. What we're building has to:

1. **Make cheating structurally impossible.** Agent metrics must be trustworthy without auditing every code block.
2. **Compose across runs.** Knowledge from past experiments shapes future ones, on the same problem and across problems.
3. **Stay reproducible.** Every experiment is a tracked, replayable artifact: code, config, data version, metric.
4. **Be portable.** Point at any local repo or git URL via the `Workspace` abstraction; don't make users rewrite their pipeline to use Dojo.

### Three-level hierarchy

```
Domain (human-defined)
  ├── Workspace                   — pre-configured execution env (local repo / git url / empty)
  ├── Task (typed, currently only RegressionTask)
  │     ├── load_data tool        — frozen at task-freeze time
  │     └── evaluate tool         — frozen at task-freeze time
  └── Experiments                 — agent-created, many per domain
        └── Knowledge atoms       — produced, linked across experiments via KnowledgeLinker
```

The Task pins the contract; the agent operates inside it. Knowledge is the framework's long-term output.

---

## 2. Positioning & strategic stance

This stance is **load-bearing** for everything that follows. Read before proposing new features.

### Open-core, already open

Dojo is open source. This repo is the **execution layer** and stays open. The hard parts that we'll close once they exist:

| Layer | Status | Plan |
|---|---|---|
| Domain abstraction, experiment loop, knowledge atoms, agent orchestration core | Open (this repo) | Stays open |
| Local adapters (storage, sandbox, compute, MLflow tracker) | Open (this repo) | Stays open |
| Sandboxed cloud execution (Modal-style) | Not built | Closed when built |
| Hosted memory layer (managed knowledge atom store, cross-domain retrieval) | Not built | Closed when built |
| Agent reliability layer (retries, guardrails, eval correctness, anti-cheating enforcement) | Partially built (anti-cheating) | The product/managed pieces stay closed |

### Single-tenant, local-first

There is one user, one machine, one `.dojo/` directory of JSON state. That's the assumption baked into the storage adapters and it's a feature, not a limitation:

- No multi-tenant MLflow operations problem
- No tenant isolation testing matrix
- No compliance surface area
- Data stays on the user's machine

The first time we genuinely need multi-tenancy (e.g., a hosted offering after enough validation), we add a Postgres adapter behind the existing `ExperimentStore` / `DomainStore` interfaces. Until then, **don't add tenant ids, RBAC, or SaaS-shaped APIs**.

### Bring your own Python pipeline

The integration surface is the [`Workspace`](src/dojo/core/domain.py) abstraction. Point Dojo at:

- A local path on disk, OR
- A git URL (cloned to `.dojo/workspaces/{domain_id}`), OR
- An empty dir Dojo creates fresh

Workspace setup auto-detects `pyproject.toml` (uses `uv sync`), `requirements.txt` (creates venv + pip install), or an existing `.venv`. The agent's `cwd` and `python_path` are pinned to the workspace at run-start. **Do not** build parallel adapters for Kubeflow, Airflow, Prefect, etc. — make the workspace abstraction work harder.

### MLflow as a bridge, not a platform

`MlflowTracker` sits **on top of** whatever MLflow the user already has. We never own or operate MLflow infrastructure. Single-user-per-MLflow-instance keeps it simple. If a user prefers no tracking, `FileTracker` writes JSON to `.dojo/tracking/`.

### CLI-first; HTTP and frontend are peers

The canonical surface is the terminal. A user gets from "empty directory" to "agent running" with two commands:

```bash
dojo init     # interactive (or fully flag-driven): config + workspace + task + AI tool gen + verify + freeze
dojo run      # agent runs against the current domain; events stream to terminal
```

In between, the human edits `PROGRAM.md` — Karpathy-style: a Markdown file containing the steering prompt. Iteration on `PROGRAM.md` between runs is the primary dial the user has.

CLI commands call `LabEnvironment` services directly (the same ones the FastAPI routers call) — no HTTP round-trip from the CLI. A running **Dojo** server is required *only* for the web frontend or external HTTP clients, never for the CLI itself. This means:

- The framework is fully usable in CI, scripts, headless boxes, and SSH sessions.
- The frontend (and any future SaaS) is built **on top of** the same runtime layer the CLI uses, not the other way round.
- No path is privileged — a feature must work via the CLI before we expose it to the API or UI.

**External infrastructure the user still provides** (none of which is "the Dojo server"):

| Dependency | When | Notes |
|---|---|---|
| `claude` CLI | Always (for non-stub agent runs) | Installed once by the user; inherits their auth. `ClaudeSDKClient` shells out to it. |
| MLflow tracking server | Only if `tracking.backend = mlflow` | The user's MLflow, never ours. `tracking.backend = file` removes this dependency. |
| `uv` / `python -m venv` | Once per workspace | Used by `WorkspaceService.setup()` to install the workspace's deps. |

**Honest practical caveats** of the in-process model:

- `dojo run` blocks the terminal until the run finishes. For long runs, fall back to standard Unix tooling (`nohup`, `tmux`) — we deliberately don't build a Dojo daemon.
- Persisted state (`.dojo/`) is the single source of truth. Any second process — another CLI invocation, the optional HTTP server, a `dojo runs show` from a different terminal — must read run state from disk, not from in-memory caches. This is a hard rule (see §8 cleanup notes and Phase 1 of [NEXT_STEPS.md](NEXT_STEPS.md)).
- Concurrent writes to `.dojo/` JSON files are not protected by file locks. Single-user, one-active-run-per-machine is fine; many-concurrent-agents-per-machine is out of scope until we have a shared backend.

### Out of scope (for now)

These are not "bad ideas" — they are deliberately not on the roadmap until prior steps validate the framework:

- Multi-tenancy / SaaS hosting
- Cloud sandbox / Modal / Supabase / hosted compute
- Enterprise integrations beyond MLflow (Kubeflow, Airflow, Slack, JIRA, etc.)
- Multiple task types beyond `RegressionTask` (classification, forecasting, generative)
- Multiple Tasks per Domain
- Frontend feature work beyond keeping the existing pages alive

---

## 3. Core abstractions

### 3.1 Domain

A research area, human-defined. Holds the steering prompt, accumulated knowledge, exactly one Task, and one Workspace.

| Field | Type | Notes |
|---|---|---|
| `id` | `str` (ULID) | |
| `name`, `description`, `prompt` | `str` | Steering prompt is the equivalent of `program.md` — human iterates on it |
| `status` | `DomainStatus` | `DRAFT → ACTIVE → PAUSED → COMPLETED → ARCHIVED` |
| `task` | `Task | None` | Exactly one (None during DRAFT before task is created) |
| `workspace` | `Workspace | None` | The execution env |
| `experiment_ids` | `list[str]` | Denormalized for fast queries |
| `metadata`, `config` | `dict` | Extensible |
| `created_at`, `updated_at` | `datetime` | |

**Change from current code:** the `tools: list[DomainTool]` field on `Domain` moves onto `Task.tools`. A Domain itself holds no tools — only its Task does.

### 3.2 Task (the contract)

The Task is the framework's anti-cheating mechanism. It defines what the agent is allowed to change and what is frozen.

```python
class TaskType(StrEnum):
    REGRESSION = "regression"
    # CLASSIFICATION, FORECASTING, GENERATIVE, CUSTOM are future — do not implement preemptively

class Direction(StrEnum):
    MINIMIZE = "minimize"
    MAXIMIZE = "maximize"

@dataclass
class Task:
    id: str = field(default_factory=generate_id)
    type: TaskType = TaskType.REGRESSION
    name: str = ""
    description: str = ""
    primary_metric: str = "rmse"        # filled from registry default; user can override
    direction: Direction = Direction.MINIMIZE
    tools: list[DomainTool] = field(default_factory=list)
    config: dict[str, Any] = field(default_factory=dict)  # task-specific (data path, target column, test split, etc.)
    frozen: bool = False                # once True, tools cannot be modified for any subsequent run
    created_at: datetime = ...
    updated_at: datetime = ...
```

#### Per-type registry

```python
@dataclass
class TaskTypeSpec:
    default_metric: str
    default_direction: Direction
    required_tools: list[ToolContract]    # spec of tools that must be present and frozen
    generation_prompt_template: str       # input to AI tool generation
    config_schema: dict                   # JSON schema for Task.config (e.g., target_column, test_split)

TASK_TYPE_REGISTRY: dict[TaskType, TaskTypeSpec] = {
    TaskType.REGRESSION: TaskTypeSpec(
        default_metric="rmse",
        default_direction=Direction.MINIMIZE,
        required_tools=[
            ToolContract(
                name="load_data",
                description="Load and split the dataset",
                returns_schema={"X_train": "array", "X_test": "array",
                                "y_train": "array", "y_test": "array"},
            ),
            ToolContract(
                name="evaluate",
                description="Evaluate predictions against y_test",
                params_schema={"y_pred": "array"},
                returns_schema={"rmse": "float", "r2": "float", "mae": "float"},
            ),
        ],
        generation_prompt_template=...,
        config_schema={"target_column": "str", "test_split_ratio": "float", "data_path": "str"},
    ),
}
```

#### What "frozen" means concretely

- `Task.frozen = False`: tools can be regenerated, edited, swapped. Agent runs are blocked.
- User clicks "Approve & freeze task" (or `POST /domains/{id}/task/freeze`) → `frozen = True`.
- Once frozen, every subsequent agent run loads the *exact same* tool definitions. The agent cannot modify them. Editing a frozen task requires explicitly unfreezing (which invalidates prior experiment comparisons — surface this in UI later).

### 3.3 Workspace (existing, no changes)

[`src/dojo/core/domain.py:38`](src/dojo/core/domain.py#L38). Already supports `local` / `git` / `empty` source and auto-detects `.venv` / `pyproject.toml` / `requirements.txt`. Setup happens once via `WorkspaceService.setup(domain)`; the agent reuses the prepared env on every run.

### 3.4 Experiment (minor changes)

[`src/dojo/core/experiment.py`](src/dojo/core/experiment.py). Stays scoped to a Domain (and therefore implicitly to its Task). `CodeRun` already records each `run_experiment_code` call. The state machine is unchanged: `PENDING → RUNNING → COMPLETED | FAILED → ARCHIVED`.

The training code the agent passes to `run_experiment_code` is what mirrors Karpathy's `train.py`. Per-run, that code is allowed to be anything; per-domain, what it can *do* is constrained by the Task tools available to it.

### 3.5 Knowledge atoms + linking (existing, no changes for now)

The current [`KeywordKnowledgeLinker`](src/dojo/runtime/keyword_linker.py) is fine. Atoms are immutable; links are `CREATED_BY` and `RELATED_TO`. We can swap in an agentic linker later behind the same `KnowledgeLinker` interface, but it's not on the critical path.

---

## 4. The anti-cheating boundary, in practice

This is the section that justifies the whole design. If this is wrong, nothing else matters.

### What the agent can do during a run

- Call `load_data` → returns the pre-split data. The agent never sees the un-split data and never picks the split.
- Write training code → submit it via `run_experiment_code`. This is the agent's mutable surface.
- Call `evaluate(y_pred)` → frozen tool, returns the metric dict including the primary metric.
- Call `log_metrics(metrics)` → records the metric dict to `TrackingConnector`.
- Call `write_knowledge(...)` → routes through `KnowledgeLinker`, records a finding.

### What the agent cannot do

- Modify `load_data` or `evaluate` mid-run (or between runs without unfreezing the task)
- Compute its own metric and report it as the primary metric
- Access the test set directly — the split is performed inside `load_data`
- Re-train evaluation code in the same `run_experiment_code` call

### Enforcement points

1. **Tool registration:** `collect_all_tools(lab, domain)` only includes the Task's frozen tools (plus the platform tools `create_experiment`, `complete_experiment`, `run_experiment_code`, `write_knowledge`, etc.). The agent gets exactly that set.
2. **System prompt:** the prompt explicitly tells the agent which surface it owns, and that the metric reported by `evaluate` is what counts.
3. **Tool immutability:** tools are loaded from the Task at run-start; the agent cannot register new tools at runtime.
4. **Metric source:** `complete_experiment` records the metric dict that came out of the `evaluate` tool, not anything else the agent might have computed.

### Soft enforcement (good-faith, not airtight)

The `Bash` and `Write` Claude builtins are still allowed for productivity — the agent can read files, do quick checks, etc. A truly adversarial agent could in principle bypass `evaluate` by reading data directly and computing its own score. We accept this for now because:

- Our agents are not adversarial; they're constrained-but-cooperative LLM agents.
- The structural separation (`evaluate` is frozen, `complete_experiment` records what `evaluate` returns) means even an agent computing a side metric still has to declare a metric *via the official channel* — and that's the one we trust.
- Hard enforcement (sandboxed file ACLs, network isolation) belongs in the sandboxed cloud execution layer, which is the **closed** part of the open-core split.

So: **structural anti-cheating now, hardened anti-cheating in the closed cloud layer later.**

---

## 5. AI-generated tool flow (and why it's load-bearing)

The magic of Dojo is that a user describes their data and evaluation in natural language, and the framework generates working tools. Without this, every domain requires hand-written Python — and we're back to "wire Claude to a Jupyter notebook."

### Generation flow

```
1. User creates Domain + Task (type=REGRESSION, points at workspace)
   └── User answers a small structured prompt: data file? target column? test split? extra context?

2. Framework calls AI tool generation
   └── For each ToolContract in TASK_TYPE_REGISTRY[REGRESSION].required_tools:
         build a prompt that includes:
           - the task type spec (return schema, param schema)
           - the user's natural-language context
           - the workspace tree summary (already built by WorkspaceScanner)
         call the LLM, parse the returned tool code

3. Framework verifies each generated tool        ←—— NEW: this step is missing today
   └── Run the tool in the sandbox with sample inputs
   └── Confirm output shape matches ToolContract
   └── Record verification result on the tool

4. User reviews the generated tools (UI later; CLI / API for now)
   └── Reads the code, the example output, the verification result
   └── Approves all → POST /domains/{id}/task/freeze

5. Task is now frozen — agent runs are unblocked
```

### Verification step (new)

Currently AI-generated tools are returned as suggestions and registered manually with no automated check ([api/routers/domains.py:485-533](src/dojo/api/routers/domains.py#L485-L533)). We need a verifier:

- Build sample inputs from `ToolContract.params_schema`
- Execute the tool in `LocalSandbox` against the workspace
- Parse stdout as JSON, validate against `ToolContract.returns_schema`
- Record `{"verified": True/False, "errors": [...], "sample_output": {...}}` on the tool
- Block freezing the task if any required tool failed verification

This is the difference between "vibe-checked AI output" and "the framework knows the tools work."

### Cleanup: Claude CLI vs Anthropic API

Today, runs go through the local `claude` CLI subprocess (no API key needed) but tool generation in [`api/routers/domains.py:500`](src/dojo/api/routers/domains.py#L500) calls `backend.complete()` which falls into [`agents/backends/claude.py:117-130`](src/dojo/agents/backends/claude.py#L117-L130) — a separate `anthropic.AsyncAnthropic()` client requiring `ANTHROPIC_API_KEY`. Two auth paths is confusing.

**Resolution:** route `backend.complete()` through the same `ClaudeSDKClient` mechanism as runs (one-shot configure → execute with no tools, capture the text). One auth path.

---

## 6. Architecture (hexagonal, preserved)

The ports & adapters layout stays. The new pieces fit cleanly into existing layers.

```
┌──────────────────────────────────────────────────────────────┐
│ Frontend (de-prioritized)                                     │
│ Domain overview · Domain detail · Agent chat                  │
└──────────────────────────────┬───────────────────────────────┘
                               │ HTTP / SSE
┌──────────────────────────────▼───────────────────────────────┐
│ API (FastAPI)                                                 │
│ /domains  /tasks  /experiments  /knowledge  /agent  /tracking│
└──────────────────────────────┬───────────────────────────────┘
                               │
┌──────────────────────────────▼───────────────────────────────┐
│ Runtime services                                              │
│ DomainService · TaskService (NEW) · ExperimentService         │
│ WorkspaceService · KnowledgeLinker · ToolGenerator (existing) │
│ ToolVerifier (NEW) · AgentOrchestrator                        │
│                LabEnvironment (DI dataclass)                  │
└──────────────────────────────┬───────────────────────────────┘
                               │
┌──────────────────────────────▼───────────────────────────────┐
│ Interfaces (ABCs)                                             │
│ DomainStore · ExperimentStore · MemoryStore · TrackingConnector│
│ KnowledgeLinkStore · KnowledgeLinker · ComputeBackend · Sandbox│
└──────────────────────────────┬───────────────────────────────┘
                               │
┌──────────────────────────────▼───────────────────────────────┐
│ Adapters                                                      │
│ Local (JSON) · MLflow · File tracker · Local sandbox · Local  │
│ compute · Claude / Stub agent backends                        │
└──────────────────────────────────────────────────────────────┘
```

### What changes

| Layer | Component | Change |
|---|---|---|
| `core/` | `Task`, `TaskType`, `Direction`, `ToolContract`, `TaskTypeSpec`, `TASK_TYPE_REGISTRY` | NEW — single file `core/task.py` |
| `core/` | `Domain` | Modified — `tools` field removed; `task: Task | None` added |
| `core/` | `DomainTool` | Stays as-is (now lives on Task instead of Domain) |
| `runtime/` | `TaskService` | NEW — task creation, tool generation orchestration, freezing |
| `runtime/` | `ToolVerifier` | NEW — sandbox-runs each tool and validates against ToolContract |
| `runtime/` | `DomainService` | Modified — no longer manages tools directly |
| `tools/` | `tool_generation.py` | Modified — registry-aware prompt building, returns ToolContract-shaped tools |
| `tools/` | `domain_tools.py` | Renamed to `task_tools.py`; loads tools from `domain.task.tools` instead of `domain.tools` |
| `agents/` | `prompts.py` | Modified — frame the contract clearly: agent owns training code, evaluate is the source of truth |
| `agents/` | `orchestrator.py` | Modified — block run start if `domain.task is None` or `domain.task.frozen is False` |
| `api/` | `routers/domains.py` | Modified — task and tool endpoints move under `/domains/{id}/task/...`; tool generation produces verified-but-unfrozen tools |
| `api/` | `routers/agent.py` | Modified — explicit error if domain has no frozen task |
| `storage/` | `local/domain.py` | Modified — Domain JSON serialisation includes nested Task |

### What stays the same

`Workspace`, `WorkspaceService`, `WorkspaceScanner`, `ExperimentService`, `KnowledgeLinker` (keyword-overlap), `KnowledgeLink`, all `TrackingConnector` adapters, all `Sandbox` and `ComputeBackend` adapters, all `MemoryStore` adapters, the SSE event mechanism, the entire ULID + structlog + ruff convention layer.

---

## 7. End-to-end lifecycle

The mental model for what a Dojo session looks like.

```
1. Human creates a Domain
   ├── Names it, writes a steering prompt ("Predict California housing prices...")
   └── Configures workspace (local repo / git url) → WorkspaceService.setup()

2. Human creates the Task on that Domain
   ├── Picks RegressionTask
   ├── Provides data path, target column, test split (Task.config)
   └── Optionally: extra natural-language context for tool generation

3. Framework generates tools (AI-assisted)
   ├── For each required_tool in TASK_TYPE_REGISTRY[REGRESSION]:
   │     LLM produces tool code → ToolVerifier runs in sandbox → records result
   ├── Human reviews generated tools (code + sample output + verification status)
   └── Human approves → Task.frozen = True

4. Human starts an agent run
   ├── Domain has a frozen task — orchestrator allows the run
   ├── System prompt frames the contract: agent owns training code, frozen tools own data + eval
   └── Agent enters research loop:

   5. Agent plans an experiment
      ├── Searches accumulated knowledge for the domain
      ├── Forms a hypothesis ("baseline linear regression")
      └── create_experiment(domain_id, hypothesis) → state RUNNING

   6. Agent executes
      ├── run_experiment_code(experiment_id, code=...)
      │     The code calls load_data(), trains, calls evaluate(y_pred)
      │     evaluate() returns {"rmse": 4.2, "r2": 0.87, "mae": 3.1}
      ├── log_metrics(experiment_id, those metrics)
      └── complete_experiment(experiment_id, metrics)

   7. Agent records knowledge
      └── write_knowledge(context, claim, action, confidence, evidence_ids=[experiment_id])
            → KnowledgeLinker creates new atom + RELATED_TO links to similar prior atoms

   8. Agent loops back to step 5 — uses the new knowledge to plan the next experiment
      └── Stops when max_turns reached, max_budget_usd reached, or human stops

9. Human reviews
   ├── Metric evolution chart over experiments in the domain
   ├── Knowledge atoms — what was learned
   ├── Iterates on the steering prompt
   └── Starts another run, possibly with the prompt updated
```

---

## 8. State the codebase needs to be in to ship this

### Cleanup before / during the rewrite

These are pre-existing cruft items that this rewrite touches anyway. Most are small.

1. **In-memory agent runs** ([api/routers/agent.py:19](src/dojo/api/routers/agent.py#L19)) — the `_runs` dict still holds run state. Recent commit `95faee5` started persisting runs but the in-memory store hasn't been reconciled. **Disk must be the single source of truth** — without that, a CLI-started run is invisible to a separately-running HTTP server, and vice versa, breaking the "CLI and server are peers" invariant. The fix is a Phase 1 prerequisite, not Phase 0 cleanup.
2. **Stale `AGENTS.md`** — predates Domains, Workspaces, Claude backend. Either rewrite to point at [CLAUDE.md](CLAUDE.md) or delete.
3. **Legacy `task_id` references in frontend** ([frontend/src/hooks/use-tasks.ts](frontend/src/hooks/use-tasks.ts), old pages) — drop them; the backend `Task` model is gone.
4. **Stale plan docs in `docs/`** — many are superseded by this MASTER_PLAN. Audit and delete or archive.
5. **Claude CLI vs Anthropic API split** (covered in §5) — unify auth paths.

### What this plan explicitly does *not* change

- The hexagonal architecture
- Knowledge linking implementation (`KeywordKnowledgeLinker` stays)
- The `Workspace` design and `WorkspaceService.setup()` flow
- Tracking adapters
- The agent backend interface (Claude / Stub)
- The MCP-based tool surface
- The frontend (de-prioritized; it'll continue to work, but isn't part of this plan)

---

## 9. Implementation phases (high level)

The detailed sequenced punch-list lives in [NEXT_STEPS.md](NEXT_STEPS.md). High level:

| Phase | Theme | Outcome |
|---|---|---|
| **0** ✅ | Cleanup *(done)* | Stale docs / legacy code gone; one Claude auth path; broken legacy `dojo run` reclaimed; lint clean |
| **1** ✅ | Task abstraction + disk-as-source-of-truth *(done)* | `core/task.py` exists; `Domain` holds a `Task` and a `program_path`; storage round-trips; `RunStore` interface + `LocalRunStore` adapter persist runs to `.dojo/runs/`; orchestrator writes through on every status change and every 10 events; agent router reads through on cache miss |
| **2** | CLI happy path + PROGRAM.md | `dojo init` / `dojo run` flow works in-process; current-domain state file; PROGRAM.md convention; `dojo task` / `dojo runs` / `dojo program` subcommands |
| **3** | Tool verification + anti-cheating gating | `ToolVerifier` runs every generated tool in sandbox; freeze gate enforces verification; orchestrator blocks unfrozen / unverified runs; system prompt rewritten around the contract |
| **4** | First real RegressionTask end-to-end via CLI | California housing dataset running cleanly via `dojo init && dojo run` alone; cheating + replay + knowledge accumulation tests pass |
| **5** | Reconnaissance for what's next | Knowledge linker upgrade decision; wall-clock budget decision; first external user |

Frontend work resumes only after Phase 4 — once the backend contract is solid and the CLI proves the loop, the UI changes are mechanical.

---

## 10. Karpathy autoresearch — explicit mapping

Because this is the design north star, mapping it out keeps decisions consistent.

| Karpathy autoresearch | Dojo equivalent |
|---|---|
| One repo per problem | One Domain |
| `prepare.py` (frozen) — data prep, dataloader, evaluation | `Task.tools` — `load_data` + `evaluate`, frozen at task-freeze time |
| `train.py` (agent edits) | Code passed to `run_experiment_code` per experiment |
| `program.md` (human edits) | `PROGRAM.md` file at `<workspace>/PROGRAM.md` (or domain-local fallback), loaded into `Domain.prompt` at run start |
| Fixed 5-min wall-clock budget | `max_turns` / `max_budget_usd` / future wall-clock budget on agent run |
| `val_bpb` metric, lower is better | `Task.primary_metric` + `Task.direction` (per `TaskTypeSpec`) |
| Single GPU, single host | Single-tenant, local sandbox |
| Agent edits one file (`train.py`) | Agent calls one mutable tool (`run_experiment_code`) |
| Human iterates on `program.md` between sessions | Human iterates on `Domain.prompt` between sessions |

A "Karpathy mode" Dojo Domain — once we add `GenerativeTask` later — is just `Domain(workspace=local repo) + Task(type=GENERATIVE, primary_metric="val_bpb", direction=MINIMIZE)`. Same shape, different Task type.

---

## 11. Success criteria

We'll know this design is working when:

1. **One frozen RegressionTask runs end-to-end on a real dataset.** Agent only writes training code; metrics come from the frozen evaluator; results are reproducible run-over-run.
2. **The agent cannot game the score** under good-faith use. If an agent rewrites a metric in its training code, it doesn't show up in `complete_experiment` — only what the frozen `evaluate` returned does.
3. **Knowledge accumulates across runs.** A second run on the same Domain visibly uses findings from the first.
4. **A new user can set up a domain in under 30 minutes.** Workspace + Task + AI-generated tools + freeze + first run.
5. **3 real users (outside Marcus) have run a domain to completion** on their own data — the validation gate before considering the closed cloud layer.

---

## 12. Decisions log

Pinning the calls so they don't get re-litigated. If you disagree with one of these, raise it explicitly — don't drift.

| # | Decision | Why | Date |
|---|---|---|---|
| 1 | One Task per Domain | Avoid bloat; Karpathy's pattern is one repo per task | 2026-05-03 |
| 2 | Only `RegressionTask` for now | Make one work end-to-end before adding more | 2026-05-03 |
| 3 | Typed via enum + registry, not class hierarchy | Fits the rest of the codebase (dataclasses + dispatch tables); JSON round-trips cleanly | 2026-05-03 |
| 4 | Evaluation runs as a frozen tool, not built-in framework code | Regression evaluation is too use-case-specific to hard-code; tool path is consistent and extensible | 2026-05-03 |
| 5 | Open-core, single-tenant, local-first | Validate before SaaS; keep the cheating-prevention story structural-only until cloud sandbox is built | 2026-05-03 |
| 6 | No abstraction names containing "Dojo" | Project may be renamed | 2026-05-03 |
| 7 | Frontend de-prioritized | Solidify the core contract first; UI is mechanical once the backend is right | 2026-05-03 |
| 8 | CLI is the canonical surface; HTTP and frontend are peers | A user must be able to do everything from the terminal alone, in-process, without a running server. Frontend/SaaS sit on top of the same runtime layer the CLI uses. | 2026-05-03 |
| 9 | `PROGRAM.md` is the editable steering prompt | Karpathy-style. Lives in the workspace by default. File content wins over `Domain.prompt` at run start so editing between runs takes effect without DB writes. | 2026-05-03 |

---

## 13. What's *not* in this plan

Deliberately out of scope for this rewrite. We can revisit any of these later, but they should not influence current decisions.

- **Recursive self-improvement / meta-agent.** A meta-agent that proposes hypotheses *for* the agent — interesting, but it sits *above* this layer and doesn't change anything below it.
- **Embedding-based knowledge retrieval.** Keyword overlap is fine for now; an agentic linker comes later behind the existing interface.
- **Multi-host / distributed compute.** All compute is local until the closed cloud layer.
- **Notebook-style interactive runs.** The unit is an autonomous run, not a REPL session.
- **Generic "task type plugin system".** Tasks are typed via the registry; we add new entries when we need them, not via a plugin mechanism.
