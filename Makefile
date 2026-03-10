.PHONY: dev test lint run format frontend-install frontend-dev frontend-build dev-all

dev:
	uv sync --all-extras

test:
	uv run pytest -v

lint:
	uv run ruff check src/ tests/
	uv run ruff format --check src/ tests/

format:
	uv run ruff check --fix src/ tests/
	uv run ruff format src/ tests/

run:
	uv run agentml start

# Frontend
frontend-install:
	cd frontend && npm install

frontend-dev:
	cd frontend && npm run dev

frontend-build:
	cd frontend && npm run build

# Full stack
dev-all:
	@echo "Starting frontend + backend..."
	cd frontend && npm run dev &
	uv run agentml start --no-frontend
