# AgentML

AI-powered ML experiment orchestration. Hexagonal architecture, config-driven backend selection, React dashboard.

## Prerequisites

- Python 3.13+
- [uv](https://docs.astral.sh/uv/)
- [just](https://github.com/casey/just) (task runner)
- Node.js 18+ (for frontend)

## Quick Start

```bash
# Install dependencies
just dev

# Start with the stub agent (no API key needed)
just run-stub

# Or set the backend via config
just run   # uses .agentml/config.yaml or defaults
```

Backend runs at `http://localhost:8000`, frontend at `http://localhost:5173`.

## Config

Create `.agentml/config.yaml` or use env vars:

```yaml
agent:
  backend: stub        # "stub" or "claude"
tracking:
  backend: file        # "file" or "mlflow"
```

Env var override: `AGENTML__AGENT__BACKEND=stub`

## Tests

```bash
just test       # run all tests
just lint       # check linting
just format     # auto-fix lint + format
```

## Project Structure

```
src/agentml/
  agents/       # AgentBackend ABC + backends (claude, stub)
  api/          # FastAPI app + routers
  tools/        # MCP tool definitions (experiments, knowledge, tracking)
  runtime/      # LabEnvironment (DI), ExperimentService
  core/         # Domain models, state machine
  config/       # Settings (pydantic-settings + YAML)
  storage/      # Persistence adapters
  tracking/     # FileTracker, MlflowTracker
frontend/       # React 19 + Vite + shadcn/ui
tests/          # unit, integration, e2e
```

## API

| Method | Path | Description |
|--------|------|-------------|
| POST | `/tasks` | Create + run task (sync) |
| POST | `/agent/run` | Start agent session (async + SSE) |
| GET | `/experiments` | List experiments |
| GET | `/knowledge` | List knowledge atoms |
| GET | `/health` | Health check |

See [AGENTS.md](AGENTS.md) for the full reference.
