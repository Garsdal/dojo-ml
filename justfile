# AgentML task runner — https://github.com/casey/just

# Install all deps (incl. dev + optional extras)
dev:
    uv sync --all-extras

# Run all tests
test:
    uv run pytest -v

# Lint check
lint:
    uv run ruff check src/ tests/
    uv run ruff format --check src/ tests/

# Auto-fix lint + format
format:
    uv run ruff check --fix src/ tests/
    uv run ruff format src/ tests/

# Start backend + frontend (stub agent by default)
run:
    uv run agentml start

# Start with stub agent explicitly
run-stub:
    AGENTML__AGENT__BACKEND=stub uv run agentml start

# Frontend
frontend-install:
    cd frontend && npm install

frontend-dev:
    cd frontend && npm run dev

frontend-build:
    cd frontend && npm run build

# Full stack (frontend in background + backend)
dev-all:
    cd frontend && npm run dev &
    uv run agentml start --no-frontend
