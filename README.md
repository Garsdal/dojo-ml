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
- Node.js 18+ (frontend)

## Quick Start

```bash
# 1. Install all dependencies
just dev

# 2. Run with stub agent (no API key needed — great for exploring)
just run-stub

# 3. Run with Claude agent (uses your Claude Code CLI subscription)
just run-claude
```

Backend → `http://localhost:8000` · Frontend → `http://localhost:5173`

## Claude Authentication

Dojo uses the `claude` CLI as a subprocess — it inherits whatever account you're already logged into. **No API key needed** for regular agent runs if you have Claude Code installed.

`ANTHROPIC_API_KEY` is only required for AI-assisted domain tool generation (`POST /domains/{id}/generate-tools`).

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
  agents/       # AgentBackend ABC + Claude / Stub backends
  api/          # FastAPI app + routers (/domains, /experiments, /knowledge, /agent)
  tools/        # Agent tools (experiments, knowledge, tracking) + AI tool generation
  runtime/      # LabEnvironment (DI container), ExperimentService, KnowledgeLinker
  storage/      # Local JSON adapters (domain, experiment, knowledge)
  tracking/     # FileTracker, MlflowTracker
  config/       # pydantic-settings + YAML config
frontend/       # React 19 + Vite 7 + shadcn/ui (currently de-prioritized)
tests/          # unit, integration, e2e
```

---

## Key API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/domains` | Create a research domain |
| `POST` | `/domains/{id}/tools/generate` | AI-generate `load_data` / `evaluate` tools for the task |
| `POST` | `/domains/{id}/workspace/setup` | One-time workspace prep (venv + deps) |
| `POST` | `/agent/run` | Start an agent run on a domain |
| `GET` | `/agent/runs/{id}/events` | Live SSE event stream |
| `GET` | `/experiments?domain_id=` | List experiments |
| `GET` | `/knowledge?domain_id=` | List knowledge atoms |
| `GET` | `/health` | Health check |

For architecture, conventions, and "how do I add X" recipes, see [CLAUDE.md](CLAUDE.md). For vision and the typed-Task design, see [MASTER_PLAN.md](MASTER_PLAN.md). For the ordered delivery punch-list, see [NEXT_STEPS.md](NEXT_STEPS.md).
