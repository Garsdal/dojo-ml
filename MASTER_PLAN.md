# MASTER_PLAN.md — Dojo Vision & Architecture

> **Dojo** — An AI-powered autonomous ML research platform where agents recursively explore domains, run experiments, and build a compressed, evolving knowledge base.

---

## 1. Vision

Dojo is a **prompt-to-results ML research engine**. A human defines a research *domain* — a broad area of inquiry with goals, data, and tools — and AI agents autonomously plan, execute, and learn from thousands of experiments within that domain.

The system operates on three levels of hierarchy:

```
Domain (human-defined)
  └── Experiments (agent-created, many thousands per domain)
        └── Knowledge Atoms (produced by experiments, linked across experiments & domains)
```

**Humans set up domains** (with AI assistance for tool creation). **Agents operate at the experiment level** — planning hypotheses, writing code, executing in sandboxes, recording results, and compressing findings into reusable knowledge. The knowledge base evolves over time, with atoms linked across experiments and domains through a dynamic compression process.

---

## 2. Core Concepts

### 2.1 Domains (replacing Tasks)

A **Domain** is the top-level organizational unit. It replaces the current `Task` abstraction with a richer, more persistent concept.

| Field | Type | Description |
|---|---|---|
| `id` | `str` (ULID) | Unique identifier |
| `name` | `str` | Human-readable domain name |
| `description` | `str` | What this research domain is about |
| `prompt` | `str` | Domain-specific steering prompt used to guide all agent research under this domain |
| `status` | `DomainStatus` | `DRAFT → ACTIVE → PAUSED → COMPLETED → ARCHIVED` |
| `tools` | `list[DomainTool]` | Domain-specific tools (data loaders, evaluation code, etc.) |
| `config` | `dict` | Domain-level configuration overrides (e.g., model constraints, resource limits) |
| `metadata` | `dict` | Extensible metadata (dataset info, success criteria, etc.) |
| `experiment_ids` | `list[str]` | Linked experiments |
| `created_at` | `datetime` | Creation timestamp |
| `updated_at` | `datetime` | Last update timestamp |

#### Domain-Specific Tools

Domains carry their own tooling — data loaders, evaluation harnesses, preprocessing scripts, etc. These are structured definitions the agent uses during experiments:

| Field | Type | Description |
|---|---|---|
| `id` | `str` (ULID) | Tool identifier |
| `name` | `str` | Tool name (e.g., `load_dataset`, `evaluate_model`) |
| `description` | `str` | What the tool does |
| `type` | `ToolType` | `data_loader`, `evaluator`, `preprocessor`, `custom` |
| `code` | `str` | Executable Python code for this tool |
| `parameters` | `dict` | JSON Schema for tool parameters |
| `created_by` | `str` | `"human"` or `"agent"` — who created it |
| `created_at` | `datetime` | Creation timestamp |

**Tool creation** supports two paths:
1. **Manual via API** — A human specifies name, description, code, and parameters
2. **AI-assisted** — The agent outputs structured JSON (and code) for tool definitions, which the system registers

### 2.2 Experiments (agent-created under domains)

Experiments remain the unit of execution but are now always scoped to a domain. The agent must be able to **create, modify, and complete experiments rapidly** — the overhead must be minimal to enable thousands of experiments per domain.

| Field | Type | Description |
|---|---|---|
| `id` | `str` (ULID) | Unique identifier |
| `domain_id` | `str` | Parent domain |
| `hypothesis` | `Hypothesis` | What the experiment tests |
| `config` | `dict` | Experiment configuration |
| `state` | `ExperimentState` | `PENDING → RUNNING → COMPLETED/FAILED → ARCHIVED` |
| `result` | `ExperimentResult` | Metrics, artifacts, logs, error |
| `metadata` | `dict` | Extensible metadata the agent can update freely |
| `created_at` | `datetime` | Creation timestamp |
| `updated_at` | `datetime` | Last update timestamp |

**Key change from current**: `task_id` → `domain_id`. The state machine stays the same. Agents should be able to batch-create experiments and update statuses with minimal friction.

### 2.3 Knowledge Atoms (linked, versioned, compressed)

Knowledge atoms are the durable output of the system. They are **not strictly linked to one experiment** — they live in a many-to-many relationship with experiments and domains through the knowledge linking system.

| Field | Type | Description |
|---|---|---|
| `id` | `str` (ULID) | Unique identifier |
| `context` | `str` | What situation or conditions this knowledge applies to |
| `claim` | `str` | The factual assertion |
| `action` | `str` | Recommended action based on this knowledge |
| `confidence` | `float` | 0.0–1.0 confidence score |
| `evidence_ids` | `list[str]` | Experiment IDs that support this atom |
| `version` | `int` | Version number (incremented on updates) |
| `supersedes` | `str | None` | ID of the atom this one replaces |
| `created_at` | `datetime` | Creation timestamp |
| `updated_at` | `datetime` | Last update timestamp |

---

## 3. Knowledge Linking & Evolution

This is the most significant new abstraction. Every knowledge atom produced by an experiment **must go through a linking process** — there is no "fire and forget" knowledge creation.

### 3.1 The Linking Process

When an agent produces a knowledge atom from an experiment:

```
Agent produces finding
       │
       ▼
  Linking Process
       │
       ├── Search existing atoms for semantic overlap
       │
       ├── MATCH FOUND ──► Merge / Update existing atom
       │   - Increase confidence if evidence agrees
       │   - Decrease confidence if evidence conflicts
       │   - Add experiment to evidence_ids
       │   - Increment version
       │   - Record the superseded version
       │
       └── NO MATCH ──► Create new atom
           - Link to experiment
           - Set initial confidence
           - Version = 1
```

This is **knowledge compression** — instead of accumulating thousands of duplicate or near-duplicate findings, the system continuously consolidates. The agent drives this process but the system enforces that it happens.

### 3.2 Knowledge Links (many-to-many)

A new `KnowledgeLink` entity connects atoms to experiments and domains:

| Field | Type | Description |
|---|---|---|
| `id` | `str` (ULID) | Link identifier |
| `atom_id` | `str` | Knowledge atom |
| `experiment_id` | `str` | Related experiment |
| `domain_id` | `str` | Domain (denormalized for fast queries) |
| `link_type` | `LinkType` | `created_by`, `updated_by`, `supported_by`, `contradicted_by` |
| `created_at` | `datetime` | When this link was established |

This enables:
- "Which experiments produced or modified this knowledge atom?"
- "What knowledge has this domain generated?"
- "Show me atoms relevant to domain X that were discovered in domain Y" (cross-domain knowledge)

### 3.3 Knowledge Evolution & Versioning

Every atom mutation creates a version. The system stores **snapshots** to enable knowledge evolution visualization:

| Field | Type | Description |
|---|---|---|
| `id` | `str` (ULID) | Snapshot ID |
| `atom_id` | `str` | Which atom |
| `version` | `int` | Version at snapshot time |
| `confidence` | `float` | Confidence at this point |
| `claim` | `str` | Claim text at this point |
| `evidence_ids` | `list[str]` | Evidence at this point |
| `timestamp` | `datetime` | When this snapshot was taken |

This allows the frontend to render "knowledge evolution" — how confidence and content changed over time as more experiments ran.

---

## 4. Architecture

### 4.1 Hexagonal Architecture (preserved)

The existing ports & adapters pattern stays. The key change is expanding the domain model layer and adding the knowledge linking abstraction.

```
┌──────────────────────────────────────────────────────┐
│                    Frontend (React)                    │
│  Domain Overview → Experiment List → Knowledge Graph  │
│  Agent Chat → Metric Evolution → Knowledge Evolution  │
└───────────────────────┬──────────────────────────────┘
                        │ HTTP / SSE
┌───────────────────────▼──────────────────────────────┐
│                    API Layer (FastAPI)                 │
│  /domains  /experiments  /knowledge  /agent  /config  │
└───────────────────────┬──────────────────────────────┘
                        │
┌───────────────────────▼──────────────────────────────┐
│                   Runtime Layer                        │
│  AgentOrchestrator  ExperimentService  KnowledgeLinker│
│                  LabEnvironment (DI)                   │
└───────────────────────┬──────────────────────────────┘
                        │
┌───────────────────────▼──────────────────────────────┐
│                  Interface Layer (ABCs)                │
│  DomainStore  ExperimentStore  MemoryStore  Tracking  │
│  KnowledgeLinkStore  ComputeBackend  Sandbox         │
└───────────────────────┬──────────────────────────────┘
                        │
┌───────────────────────▼──────────────────────────────┐
│               Adapter Layer (Implementations)         │
│  Local (JSON/files)  ·  MLflow  ·  Future: Postgres  │
└──────────────────────────────────────────────────────┘
```

### 4.2 New / Modified Interfaces

| Interface | Status | Methods |
|---|---|---|
| `DomainStore` | **NEW** | `save`, `load`, `list`, `delete`, `update` |
| `KnowledgeLinkStore` | **NEW** | `link`, `unlink`, `get_links_for_atom`, `get_links_for_experiment`, `get_links_for_domain`, `get_atoms_for_domain` |
| `MemoryStore` | **MODIFIED** | Add `update(atom)`, `get_version_history(atom_id)`, `get_snapshot(atom_id, version)` |
| `ExperimentStore` | **MODIFIED** | `task_id` filter → `domain_id` filter |
| `TrackingConnector` | **UNCHANGED** | Experiment-level tracking stays the same |
| `ComputeBackend` | **UNCHANGED** | — |
| `Sandbox` | **UNCHANGED** | — |
| `ArtifactStore` | **UNCHANGED** | — |

### 4.3 Runtime Services

| Service | Status | Role |
|---|---|---|
| `ExperimentService` | **MODIFIED** | Experiments now scoped to domains. Batch operations for rapid experiment creation. |
| `KnowledgeLinker` | **NEW** | Drives the linking process. Every knowledge write goes through here. The agent calls `produce_knowledge(finding, experiment_id, domain_id)` → linker searches, merges or creates, links, and versions. |
| `DomainService` | **NEW** | CRUD + tool management for domains. Creates agent runs scoped to a domain. |
| `LabEnvironment` | **MODIFIED** | Add `domain_store`, `knowledge_link_store` fields. |

### 4.4 Agent System

The `AgentOrchestrator` is extended to be domain-aware:

1. **Domain-scoped runs** — When an agent runs, it receives the domain's steering prompt, available domain-specific tools, and accumulated knowledge
2. **Recursive experiment creation** — The agent plans, creates, and executes experiments in a loop. It can create many experiments within a single run
3. **Mandatory knowledge linking** — The agent's `write_knowledge` tool now routes through `KnowledgeLinker` instead of directly into `MemoryStore`. The tool returns linking results so the agent knows whether it created new knowledge or merged with existing
4. **Domain tool injection** — Domain-specific tools are registered as additional `ToolDef` entries and injected into the agent's available tools at run time

#### Updated Agent Tools

| Tool | Change | Description |
|---|---|---|
| `create_experiment` | **Modified** | Now requires `domain_id` instead of `task_id` |
| `complete_experiment` | Unchanged | — |
| `fail_experiment` | Unchanged | — |
| `write_knowledge` | **Modified** | Routes through `KnowledgeLinker`. Returns linking result (created/merged/atom_id/version) |
| `search_knowledge` | **Modified** | Optional `domain_id` filter for domain-scoped search |
| `list_knowledge` | **Modified** | Optional `domain_id` filter |
| `log_metrics` | Unchanged | — |
| `log_params` | Unchanged | — |
| `compare_experiments` | **Modified** | Can filter by `domain_id` |
| *Domain tools* | **New** | Dynamic tools from domain definition injected per-run |

---

## 5. API Design

### 5.1 Domain Endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/domains` | Create a domain (name, description, prompt, optional tools) |
| `GET` | `/domains` | List all domains with status summary |
| `GET` | `/domains/{id}` | Get domain with experiment count, knowledge count, agent status |
| `PUT` | `/domains/{id}` | Update domain (prompt, metadata, status) |
| `DELETE` | `/domains/{id}` | Archive/delete domain |
| `POST` | `/domains/{id}/tools` | Add a domain-specific tool (manual or AI-generated JSON) |
| `GET` | `/domains/{id}/tools` | List domain tools |
| `PUT` | `/domains/{id}/tools/{tool_id}` | Update a domain tool |
| `DELETE` | `/domains/{id}/tools/{tool_id}` | Remove a domain tool |
| `POST` | `/domains/{id}/generate-tools` | AI-assisted: agent generates tool definitions for the domain |

### 5.2 Experiment Endpoints (modified)

| Method | Path | Description |
|---|---|---|
| `GET` | `/experiments?domain_id=` | List experiments, filterable by domain |
| `GET` | `/experiments/{id}` | Get experiment detail |
| `GET` | `/domains/{id}/experiments` | List experiments for a domain |
| `GET` | `/domains/{id}/metrics` | Metric evolution across all experiments in a domain |

### 5.3 Knowledge Endpoints (modified)

| Method | Path | Description |
|---|---|---|
| `GET` | `/knowledge?domain_id=` | List atoms, filterable by domain via links |
| `GET` | `/knowledge/{id}` | Get atom with full version history and links |
| `GET` | `/knowledge/{id}/history` | Version history for an atom |
| `GET` | `/knowledge/relevant?query=&domain_id=&limit=` | Search with optional domain scoping |
| `POST` | `/knowledge` | Direct atom creation (still goes through linker) |
| `DELETE` | `/knowledge/{id}` | Delete atom |
| `GET` | `/domains/{id}/knowledge` | All knowledge atoms linked to a domain |
| `GET` | `/domains/{id}/knowledge/evolution` | Knowledge evolution snapshots for a domain |

### 5.4 Agent Endpoints (modified)

| Method | Path | Description |
|---|---|---|
| `POST` | `/agent/run` | Start agent run (now requires `domain_id`) |
| `GET` | `/agent/runs?domain_id=` | List runs, filterable by domain |
| `GET` | `/agent/runs/{id}` | Get run detail |
| `POST` | `/agent/runs/{id}/stop` | Stop a running agent |
| `GET` | `/agent/runs/{id}/events` | SSE event stream |

### 5.5 Retained Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Health check |
| `GET` | `/config` | Public config summary |
| `GET` | `/tracking/{experiment_id}/metrics` | Per-experiment tracked metrics |

---

## 6. Frontend

### 6.1 Design Philosophy

**Super lean.** Three levels of hierarchy: Domain → Experiments → Knowledge. Agents operate at the experiment level. Humans set up domains (with AI help for tool creation).

### 6.2 Pages

#### Main Page — Domain Overview (`/`)

- **Empty state**: If no domains exist, show a centered prompt: *"Create your first research domain"* with a create button
- **Domain list**: Card grid showing each domain with:
  - Name, description, status badge
  - Experiment count (running / total)
  - Knowledge atom count
  - Active agent indicator (running / idle)
  - Last activity timestamp
- **Create domain** button → modal/drawer with form

#### Domain Page (`/domains/{id}`)

A single page with sections, not sub-routes:

**Header**
- Domain name, status, description
- Domain steering prompt (collapsible)
- Edit / Pause / Resume actions

**Experiments Section**
- Running agents and which experiments they're working on (live)
- Experiment table/list: status, hypothesis, key metrics, timestamp
- Quick filters: status, date range

**Metric Evolution Chart**
- Line chart showing key metrics across experiments over time
- Selectable metrics (from tracking data)
- Zoom, hover for experiment detail

**Knowledge Evolution Chart**
- Timeline visualization of knowledge atoms
- Shows: new atoms created, existing atoms updated, confidence changes over time
- Can drill into specific atom version history

**Domain Tools Section**
- List of registered tools with name, type, description
- Click to expand: see code, parameters, creation source (human/agent)
- Add tool button (manual or AI-assisted)

**Agent Chat / Output Window**
- When an agent is running: live streaming output (SSE events)
- Shows which experiment the agent is currently working on
- Historical run output for completed runs
- Start new run / stop current run controls

### 6.3 Removed / Simplified Pages

The current multi-page layout (Dashboard, Tasks, Experiments, Knowledge, Agent) collapses to:

| Old | New |
|---|---|
| Dashboard | → Domain overview (main page) |
| Tasks | → **Removed** (replaced by domains) |
| Experiments | → Section in domain page |
| Knowledge | → Section in domain page + cross-domain search if needed |
| Agent | → Section in domain page |

### 6.4 Frontend Data Flow

```
useDomains()           → GET /domains
useDomain(id)          → GET /domains/{id}
useDomainExperiments() → GET /domains/{id}/experiments
useDomainMetrics()     → GET /domains/{id}/metrics
useDomainKnowledge()   → GET /domains/{id}/knowledge
useDomainTools()       → GET /domains/{id}/tools
useKnowledgeEvolution()→ GET /domains/{id}/knowledge/evolution
useAgentRuns(domainId) → GET /agent/runs?domain_id=
useAgentEvents(runId)  → GET /agent/runs/{id}/events (SSE)
```

---

## 7. Data Flow: End-to-End Lifecycle

```
1. Human creates a Domain
   ├── Defines name, description, steering prompt
   ├── Optionally adds domain-specific tools (or asks AI to generate them)
   └── Domain status → ACTIVE

2. Human starts an Agent Run on the domain
   ├── Agent receives: domain prompt + accumulated knowledge + domain tools
   └── Agent enters research loop:

   3. Agent plans experiment
      ├── Searches existing knowledge
      ├── Identifies gaps or hypotheses to test
      └── Creates experiment (state → RUNNING)

   4. Agent executes experiment
      ├── Writes code (using domain tools + sandbox)
      ├── Runs code, collects results
      ├── Logs metrics and params to tracking
      └── Completes or fails experiment

   5. Agent produces knowledge
      ├── Formulates finding as knowledge atom
      ├── Calls write_knowledge (→ KnowledgeLinker)
      │   ├── Linker searches for semantic overlap
      │   ├── MATCH: Merges with existing atom, increments version
      │   └── NO MATCH: Creates new atom, version 1
      ├── Links created: atom ↔ experiment ↔ domain
      └── Snapshot recorded for evolution tracking

   6. Agent loops back to step 3
      ├── Uses updated knowledge to plan next experiment
      ├── May create dozens/hundreds of experiments per run
      └── Stops when: max turns reached / human stops / goals met

7. Human reviews results
   ├── Metric evolution chart shows progress over time
   ├── Knowledge evolution shows what was learned
   ├── Can start new agent runs to continue research
   └── Can pause, reconfigure, or archive the domain
```

---

## 8. Implementation Plan

### Phase 1: Domain Foundation

**Goal**: Replace tasks with domains, maintain all current functionality.

1. **Core domain model** — Create `Domain`, `DomainTool`, `DomainStatus` in `core/`
2. **DomainStore interface** — ABC in `interfaces/`
3. **LocalDomainStore adapter** — JSON file persistence in `storage/`
4. **Refactor Experiment** — `task_id` → `domain_id` throughout
5. **Domain API routes** — Full CRUD + tool management
6. **DomainService** — Runtime orchestration
7. **Update LabEnvironment** — Add `domain_store`
8. **Update build_lab** — Wire `DomainStore`
9. **Migrate agent tools** — `create_experiment` takes `domain_id`
10. **Tests** — Unit + E2E for domain lifecycle

### Phase 2: Knowledge Linking & Evolution

**Goal**: Knowledge atoms are linked, versioned, and compressed.

1. **KnowledgeLink model** — `core/knowledge.py`
2. **KnowledgeSnapshot model** — Version history
3. **KnowledgeLinkStore interface** — ABC in `interfaces/`
4. **LocalKnowledgeLinkStore** — JSON file adapter
5. **KnowledgeLinker service** — Runtime linking logic (search → merge-or-create → link → snapshot)
6. **Update MemoryStore interface** — Add `update`, `get_version_history`
7. **Update write_knowledge tool** — Route through linker, return linking results
8. **Update search_knowledge tool** — Add `domain_id` filter
9. **Knowledge evolution API endpoints** — Version history, snapshots
10. **Tests** — Linking, merging, versioning round-trips

### Phase 3: Domain-Scoped Agent Runs

**Goal**: Agents are domain-aware and use domain tools.

1. **Domain-scoped system prompt** — Include domain steering prompt and accumulated knowledge
2. **Domain tool injection** — Register domain tools as `ToolDef` entries at run time
3. **Agent run scoped to domain** — Require `domain_id` on agent run creation
4. **Recursive experiment loop** — Agent can create/complete many experiments per run
5. **Update agent router** — Domain-scoped run creation and listing
6. **Metric evolution endpoint** — Aggregate metrics across domain experiments
7. **Tests** — Agent run with domain tools, multiple experiments per run

### Phase 4: Frontend Redesign

**Goal**: Lean domain-centric UI.

1. **Domain overview page** — Replace dashboard, empty state, domain cards
2. **Domain detail page** — Experiments section with live agent status
3. **Metric evolution chart** — Line chart with selectable metrics
4. **Knowledge evolution chart** — Timeline of atom changes
5. **Domain tools section** — List, detail, add (manual + AI-assisted)
6. **Agent chat window** — SSE streaming, run history
7. **Remove old pages** — Tasks page, standalone experiment/knowledge pages
8. **New hooks** — `useDomains`, `useDomainExperiments`, `useKnowledgeEvolution`, etc.

### Phase 5: AI-Assisted Tool Generation

**Goal**: Agent can generate domain-specific tool definitions.

1. **Tool generation prompt** — Given domain description, generate data loader / evaluator definitions
2. **Structured output** — Agent returns JSON `DomainTool` definitions + code
3. **Validation & registration** — Parse, validate, and register tools via API
4. **Sandbox testing** — Optionally test generated tools in sandbox before registering
5. **UI flow** — "Generate tools" button on domain page, review & approve

---

## 9. What Stays The Same

The following existing abstractions and implementations require **no major changes**:

| Component | Why it stays |
|---|---|
| `ExperimentState` state machine | Same transitions: PENDING → RUNNING → COMPLETED/FAILED → ARCHIVED |
| `ExperimentService` | Same lifecycle orchestration, just scoped to domains |
| `AgentBackend` interface | Claude/Stub backends unchanged — they execute prompts and yield events |
| `AgentOrchestrator` | Same event loop, just receives domain context |
| `ToolDef` / `ToolRegistry` | Same tool framework — domain tools are just more `ToolDef` instances |
| `ToolAdapter` (Claude adapter) | No changes — converts `ToolDef` to SDK format |
| `Sandbox` / `ComputeBackend` | Unchanged |
| `ArtifactStore` | Unchanged |
| `TrackingConnector` | Unchanged — still logs per-experiment |
| `FileTracker` / `MlflowTracker` | Unchanged |
| Config / Settings system | Extended with `DomainSettings` but core mechanism the same |
| SSE streaming | Same mechanism, domain-scoped |

---

## 10. Key Design Decisions

### 10.1 Knowledge atoms are many-to-many, not owned by experiments

An atom can be linked to experiments across multiple domains. The `KnowledgeLink` table is the authoritative relationship. `evidence_ids` on the atom itself is a convenience denormalization.

### 10.2 Knowledge linking is mandatory, not optional

Every `write_knowledge` call goes through `KnowledgeLinker`. The agent cannot bypass this. This ensures knowledge compression happens continuously and the knowledge base doesn't bloat with duplicates.

### 10.3 Domains are persistent, agent runs are ephemeral-ish

Domains are first-class persisted entities. Agent runs are important for observability but the lasting value is in the experiments and knowledge they produce. Runs should be persisted (unlike current in-memory storage) but are secondary to domains.

### 10.4 Domain tools are code, not just descriptions

Domain tools contain actual executable code. The agent uses them via the standard `ToolDef` mechanism. This means domain tools are sandboxed and have the same execution model as other agent tools.

### 10.5 Versioned knowledge over mutable knowledge

Knowledge atoms are versioned rather than silently mutated. Every change creates a snapshot. The current version is the "live" one, but history is always available. This supports knowledge evolution visualization and auditability.

### 10.6 Frontend is domain-first, not feature-first

The UI is organized around domains, not around "experiments page" or "knowledge page". A domain page is the single pane of glass for everything happening in that research area.

---

## 11. Current State vs. Target

| Capability | Current State | Target State |
|---|---|---|
| Top-level entity | `Task` (in-memory, minimal) | `Domain` (persisted, rich metadata, tools) |
| Domain-specific tools | None | Full tool authoring (manual + AI-generated) |
| Experiment scoping | `task_id` (loose) | `domain_id` (strict, persisted) |
| Knowledge linking | None (atoms are standalone) | Many-to-many via `KnowledgeLink` |
| Knowledge versioning | None | Full version history + snapshots |
| Knowledge compression | None | `KnowledgeLinker` (search → merge-or-create) |
| Knowledge search | Keyword only | Keyword + domain filter (future: embedding) |
| Agent domain awareness | Basic task prompt | Domain prompt + accumulated knowledge + domain tools |
| Metric evolution | Per-experiment only | Domain-wide aggregation over time |
| Knowledge evolution | None | Timeline of atom changes per domain |
| Frontend structure | 5 separate pages | 2 pages: domain overview + domain detail |
| Agent run persistence | In-memory | Persisted |
| Tool creation | Static (code-defined) | Dynamic (API + AI-generated) |

---

## 12. File Structure (target)

```
src/dojo/
├── core/
│   ├── domain.py          # Domain, DomainTool, DomainStatus
│   ├── experiment.py       # Experiment (domain_id replaces task_id)
│   ├── knowledge.py        # KnowledgeAtom (+ version, supersedes fields)
│   ├── knowledge_link.py   # KnowledgeLink, KnowledgeSnapshot, LinkType
│   └── state_machine.py    # Unchanged
│
├── interfaces/
│   ├── domain_store.py     # NEW: DomainStore ABC
│   ├── knowledge_link_store.py  # NEW: KnowledgeLinkStore ABC
│   ├── experiment_store.py # Modified: domain_id filter
│   ├── memory_store.py     # Modified: update, version history
│   └── ...                 # Others unchanged
│
├── storage/
│   ├── local_domain.py     # NEW: LocalDomainStore (JSON)
│   ├── local_knowledge_link.py  # NEW: LocalKnowledgeLinkStore (JSON)
│   └── ...                 # Others adapted
│
├── runtime/
│   ├── lab.py              # Modified: + domain_store, knowledge_link_store
│   ├── experiment_service.py  # Modified: domain-scoped
│   ├── knowledge_linker.py    # NEW: KnowledgeLinker service
│   └── domain_service.py     # NEW: DomainService
│
├── agents/
│   ├── orchestrator.py     # Modified: domain-aware context injection
│   ├── prompts.py          # Modified: domain steering prompt
│   └── ...                 # Backends unchanged
│
├── tools/
│   ├── experiments.py      # Modified: domain_id
│   ├── knowledge.py        # Modified: routes through linker, domain filter
│   ├── domain_tools.py     # NEW: dynamic tool registration from domain
│   └── ...                 # Others unchanged
│
├── api/
│   ├── routers/
│   │   ├── domains.py      # NEW: domain CRUD + tools
│   │   ├── experiments.py  # Modified: domain scoping
│   │   ├── knowledge.py    # Modified: domain filter, evolution endpoints
│   │   ├── agent.py        # Modified: domain-scoped runs
│   │   └── ...             # Others unchanged
│   ├── app.py              # Modified: register domain router
│   └── deps.py             # Modified: build domain_store, knowledge_link_store
│
└── config/
    └── settings.py         # Extended: domain defaults if needed

frontend/src/
├── pages/
│   ├── domain-overview.tsx    # Main page — domain cards or empty state
│   └── domain-detail.tsx      # Single domain — experiments, metrics, knowledge, tools, agent
│
├── components/
│   ├── domains/
│   │   ├── domain-card.tsx
│   │   ├── domain-form.tsx
│   │   └── domain-tools-section.tsx
│   ├── experiments/
│   │   └── experiment-table.tsx
│   ├── charts/
│   │   ├── metric-evolution.tsx
│   │   └── knowledge-evolution.tsx
│   ├── knowledge/
│   │   └── knowledge-timeline.tsx
│   └── agent/
│       └── agent-chat.tsx
│
├── hooks/
│   ├── use-domains.ts
│   ├── use-domain.ts
│   ├── use-domain-experiments.ts
│   ├── use-domain-knowledge.ts
│   ├── use-domain-metrics.ts
│   ├── use-knowledge-evolution.ts
│   └── use-agent.ts          # Modified: domain-scoped
│
└── types.ts                  # Extended: Domain, DomainTool, KnowledgeLink, etc.
```

---

## 13. Summary

Dojo evolves from a task-based experiment runner into a **domain-driven research platform** where:

- **Humans define the "what"** — research domains with goals, data, and tools
- **Agents handle the "how"** — recursively planning, executing, and learning from experiments
- **Knowledge compounds** — through mandatory linking, versioning, and compression
- **Everything is observable** — metric evolution, knowledge evolution, live agent output

The core hexagonal architecture holds. The main additions are the domain model, knowledge linking layer, and a simplified domain-centric frontend. Most existing interfaces and adapters require only minor modifications (scoping to domains) rather than rewrites.
