# 🥋 Dojo — An AI-powered autonomous ML research framework.

<div align="center">
  <img src="assets/dojo-logo-no-bg.png" alt="Dojo.ml logo" width="200" />

  <p><strong>Run controlled, reproducible ML experiments on your existing pipelines and build a memory of what actually works.</strong></p>
</div>

---

<div align="center">
  <video src="https://github.com/user-attachments/assets/c0ff01d5-2c2d-408f-a2fd-22cc6d400e2c" alt="Dojo test example" width="800" controls></video>
</div>

---

## What is Dojo?

You define a **domain** — a research area pointing at your data with a fixed evaluation contract. An AI agent runs experiments inside that contract: writing training code, calling frozen `load_data` and `evaluate` tools, logging metrics, and recording findings as durable knowledge atoms.

```
Domain (you define)
  ├── Task            — the contract: load_data + evaluate (frozen, AI-generated at setup)
  ├── Workspace       — your repo / pipeline (local path or git url)
  └── Experiments     — agent-created, many per domain
        └── Knowledge atoms — linked across experiments, accumulating over time
```

The agent owns the training code. The framework owns evaluation. That separation is what makes the metrics trustworthy run-over-run, and what makes it safe to leave the agent unsupervised.

Inspired by [Karpathy's autoresearch](https://github.com/karpathy/autoresearch) — `prepare.py` is frozen, `train.py` is fair game, `program.md` is what the human iterates on. Dojo generalises that pattern to any well-defined ML problem class.

---

## Current Status

> **⚠️ Proof of Concept** — under active development. Open source. Single-tenant, local-first, by design.

- **Agent**: Claude Agent SDK (uses your local `claude` CLI auth — no API key needed for runs)
- **Compute**: Local only (in-process / subprocess) — your data stays on your machine
- **Storage**: Local JSON files in `.dojo/`
- **Tracking**: File-based or MLflow (sits on top of an MLflow you already run)
- **Tasks supported**: `RegressionTask` (more types to come once regression is solid)

---

## Prerequisites

- Python 3.13+
- [uv](https://docs.astral.sh/uv/)
- [just](https://github.com/casey/just)
- The `claude` CLI logged in (Claude Code) — Dojo shells out to it; no `ANTHROPIC_API_KEY` needed
- Node.js 18+ (only if you want the web UI)

```bash
just dev                     # install backend + frontend deps
```

## Getting Started — California Housing in 4 commands

The CLI is a peer of the HTTP API, not a thin wrapper around it. The whole happy path runs in-process — no server needed.

```bash
mkdir housing && cd housing

# 1. Scaffold the domain (creates .dojo/, the regression Task, and PROGRAM.md)
dojo init --name housing --task-type regression --non-interactive

# 2. Describe the dataset, target, and what success looks like
$EDITOR PROGRAM.md

# 3. AI generates load_data + evaluate from PROGRAM.md, verifies them against
#    the regression contract, and freezes the task. Re-run after edits.
dojo task setup

# 4. Run the agent — events stream live to your terminal
dojo run --max-turns 30
```

A reasonable starter `PROGRAM.md` for California housing:

```markdown
## Goal
Predict California median house value (regression). Minimise RMSE on a 20% held-out test split.

## Dataset
Use `sklearn.datasets.fetch_california_housing(return_X_y=True)`.
Features and target both come back as numpy arrays — no column names needed.
https://scikit-learn.org/stable/modules/generated/sklearn.datasets.fetch_california_housing.html

## Target
Median house value (in $100,000s) for census blocks in California.

## Success
Beat a linear baseline. Try at least one tree-based model. Avoid overfitting.
```

What happens under the hood:

- **`dojo init`** writes `.dojo/config.yaml`, creates the domain + regression task with `expected_metrics = [rmse, r2, mae]`, scaffolds `PROGRAM.md`, and sets `current_domain_id`.
- **`dojo task setup`** reads `PROGRAM.md`, asks the AI to generate `load_data` + `evaluate`, runs each tool in a sandbox against its `ToolContract`, and freezes the task. Verification failures tell you which tool failed and why — fix `PROGRAM.md` (or the tool code) and re-run.
- **`dojo run`** starts the agent in-process. The agent writes training code; `load_data` and `evaluate` stay frozen. The metric dict from `evaluate` is the only source of truth — `complete_experiment` rejects metric keys outside the contract, so the agent can't smuggle in custom numbers.

Useful neighbours:

```bash
dojo task show               # current task status, tools, frozen?
dojo runs ls                 # recent runs
dojo runs show               # last run's events + cost
dojo program show            # print the live PROGRAM.md
dojo domain use <name>       # switch active domain
```

## Running the server (optional)

If you want the web UI or HTTP API:

```bash
just run-stub                # stub agent (no LLM, deterministic)
just run-claude              # Claude agent (uses your local CLI auth)
```

Backend → `http://localhost:8000` · Frontend → `http://localhost:5173`. The server reads the same `.dojo/` your CLI commands write to, so a CLI-started run is visible in the UI and vice versa.

---

## Config

Create `.dojo/config.yaml` in your project root:

```yaml
agent:
  backend: stub        # "stub" (no LLM) or "claude"
tracking:
  backend: file        # "file" or "mlflow"
```

Or use environment variables:

```bash
DOJO_AGENT__BACKEND=claude
DOJO_TRACKING__BACKEND=mlflow
```

---

## Tests

```bash
just test       # all tests
just lint       # ruff check
just format     # auto-fix lint + format
```

---

## Project Structure

```
src/dojo/
  core/         # Domain, Task, Experiment, KnowledgeAtom, Workspace, state machine
  agents/       # AgentBackend ABC + Claude / Stub backends, orchestrator
  api/          # FastAPI app + routers (/domains, /experiments, /knowledge, /agent)
  cli/          # Typer CLI: init, run, task, runs, program, domain, config, start
  tools/        # Agent tools (experiments, knowledge, tracking) + AI tool generation
  runtime/      # LabEnvironment (DI), ExperimentService, ToolVerifier, program loader
  sandbox/      # LocalSandbox (subprocess); runs generated tools + agent code
  compute/      # Compute backends (LocalCompute today)
  storage/      # Local JSON adapters (domain, experiment, knowledge, run)
  tracking/     # FileTracker, MlflowTracker, NoopTracker
  config/       # pydantic-settings + YAML config
frontend/       # React 19 + Vite 7 + shadcn/ui (currently de-prioritized)
tests/          # unit, integration, e2e
```

---

## Key API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/domains` | Create a research domain |
| `POST` | `/domains/{id}/task` | Attach a Task (regression today) |
| `POST` | `/domains/{id}/tools/generate` | AI-generate `load_data` / `evaluate` from PROGRAM.md, verify against contract |
| `POST` | `/domains/{id}/task/freeze` | Freeze the task — gated on every required tool's verification |
| `POST` | `/domains/{id}/workspace/setup` | One-time workspace prep (venv + deps) |
| `POST` | `/agent/run` | Start an agent run on a domain (requires a frozen task) |
| `GET` | `/agent/runs/{id}/events` | Live SSE event stream |
| `GET` | `/experiments?domain_id=` | List experiments |
| `GET` | `/knowledge?domain_id=` | List knowledge atoms |
| `GET` | `/health` | Health check |

For architecture, conventions, and "how do I add X" recipes, see [CLAUDE.md](CLAUDE.md). For vision and the typed-Task design, see [MASTER_PLAN.md](MASTER_PLAN.md). For the ordered delivery punch-list, see [NEXT_STEPS.md](NEXT_STEPS.md).
