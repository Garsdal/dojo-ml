# Dojo.ml task runner — https://github.com/casey/just

# ── Development ───────────────────────────────────────────────────────────────

# Install all deps (incl. dev + optional extras) and frontend
dev:
    uv sync --all-extras
    cd frontend && npm install

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

# ── Running ───────────────────────────────────────────────────────────────────

# Start with stub agent (no API key required)
run-stub *ARGS:
    DOJO_AGENT__BACKEND=stub uv run dojo start {{ARGS}}

# Start with Claude agent (uses claude CLI subscription; ANTHROPIC_API_KEY only needed for domain tool generation)
run-claude *ARGS:
    DOJO_AGENT__BACKEND=claude uv run dojo start {{ARGS}}

# Start with stub agent + MLflow tracking (MLflow UI on :8080)
run-stub-mlflow *ARGS:
    PYTHONWARNINGS=ignore::FutureWarning uv run mlflow server --backend-store-uri ./mlruns --host 127.0.0.1 --port 8080 2>/dev/null &
    @sleep 2
    DOJO_AGENT__BACKEND=stub \
    DOJO_TRACKING__BACKEND=mlflow \
    DOJO_TRACKING__MLFLOW_TRACKING_URI=http://127.0.0.1:8080 \
    uv run dojo start {{ARGS}}

# Start with Claude agent + MLflow tracking (MLflow UI on :8080)
run-claude-mlflow *ARGS:
    PYTHONWARNINGS=ignore::FutureWarning uv run mlflow server --backend-store-uri ./mlruns --host 127.0.0.1 --port 8080 2>/dev/null &
    @sleep 2
    DOJO_AGENT__BACKEND=claude \
    DOJO_TRACKING__BACKEND=mlflow \
    DOJO_TRACKING__MLFLOW_TRACKING_URI=http://127.0.0.1:8080 \
    uv run dojo start {{ARGS}}

# Stop all services (backend :8000, frontend :5173, MLflow :8080)
stop:
    -lsof -ti :8000 | xargs kill -9
    -lsof -ti :5173 | xargs kill -9
    -lsof -ti :8080 | xargs kill -9

# ── Frontend ──────────────────────────────────────────────────────────────────

frontend-install:
    cd frontend && npm install

frontend-dev:
    cd frontend && npm run dev

frontend-build:
    cd frontend && npm run build

# ── Misc ──────────────────────────────────────────────────────────────────────

# Run frontend in background + backend (without built-in frontend server)
dev-all:
    cd frontend && npm run dev &
    uv run dojo start --no-frontend
