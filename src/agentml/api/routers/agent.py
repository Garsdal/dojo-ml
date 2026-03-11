"""Agent router — start, monitor, and stop agent research sessions."""

import asyncio
import json

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from agentml.agents.factory import create_agent_backend
from agentml.agents.orchestrator import AgentOrchestrator
from agentml.agents.types import AgentRun, RunStatus, ToolHint
from agentml.runtime.lab import LabEnvironment

router = APIRouter(prefix="/agent", tags=["agent"])

# In-memory store of active and completed runs
_runs: dict[str, AgentRun] = {}
_orchestrators: dict[str, AgentOrchestrator] = {}
_background_tasks: set[asyncio.Task[None]] = set()


def _get_lab(request: Request) -> LabEnvironment:
    return request.app.state.lab


# --- Request/Response models ---


class ToolHintRequest(BaseModel):
    name: str
    description: str
    source: str
    code_template: str = ""


class StartRunRequest(BaseModel):
    prompt: str
    domain_id: str | None = None
    tool_hints: list[ToolHintRequest] = []
    max_turns: int = 50
    max_budget_usd: float | None = None


class AgentEventResponse(BaseModel):
    id: str
    timestamp: str
    event_type: str
    data: dict


class AgentRunResponse(BaseModel):
    id: str
    domain_id: str
    prompt: str
    status: str
    events: list[AgentEventResponse] = []
    started_at: str | None = None
    completed_at: str | None = None
    total_cost_usd: float | None = None
    num_turns: int = 0
    error: str | None = None


# --- Routes ---


@router.post("/run", response_model=AgentRunResponse)
async def start_run(body: StartRunRequest, request: Request) -> AgentRunResponse:
    """Start an agent research session."""
    lab = _get_lab(request)
    settings = request.app.state.settings

    # Create the backend from config (e.g. "claude", "stub")
    backend = create_agent_backend(settings.agent.backend)

    orchestrator = AgentOrchestrator(
        lab,
        backend,
        max_turns=body.max_turns,
        max_budget_usd=body.max_budget_usd,
        permission_mode=settings.agent.permission_mode,
        cwd=settings.agent.cwd,
    )

    # Convert tool hints from request to domain type
    tool_hints = [
        ToolHint(
            name=h.name,
            description=h.description,
            source=h.source,
            code_template=h.code_template,
        )
        for h in body.tool_hints
    ]

    run = await orchestrator.start(
        prompt=body.prompt, domain_id=body.domain_id, tool_hints=tool_hints
    )

    _runs[run.id] = run
    _orchestrators[run.id] = orchestrator

    # Execute in background
    task = asyncio.create_task(_run_agent(run, orchestrator))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)

    return _to_response(run)


@router.get("/runs", response_model=list[AgentRunResponse])
async def list_runs() -> list[AgentRunResponse]:
    """List all agent runs."""
    return [_to_response(r) for r in _runs.values()]


@router.get("/runs/{run_id}", response_model=AgentRunResponse)
async def get_run(run_id: str) -> AgentRunResponse:
    """Get agent run status and events."""
    run = _runs.get(run_id)
    if not run:
        raise HTTPException(404, f"Run {run_id} not found")
    return _to_response(run)


@router.post("/runs/{run_id}/stop")
async def stop_run(run_id: str) -> dict:
    """Stop a running agent."""
    orchestrator = _orchestrators.get(run_id)
    if not orchestrator:
        raise HTTPException(404, f"Run {run_id} not found")
    await orchestrator.stop()
    return {"status": "stopped"}


@router.get("/runs/{run_id}/events")
async def stream_events(run_id: str) -> EventSourceResponse:
    """Server-Sent Events stream for an agent run."""
    run = _runs.get(run_id)
    if not run:
        raise HTTPException(404, f"Run {run_id} not found")

    async def event_generator():
        seen = 0
        while True:
            # Yield new events
            while seen < len(run.events):
                event = run.events[seen]
                seen += 1
                yield {
                    "event": event.event_type,
                    "data": json.dumps(
                        {
                            "id": event.id,
                            "timestamp": event.timestamp.isoformat(),
                            "event_type": event.event_type,
                            "data": event.data,
                        },
                        default=str,
                    ),
                }

            # Check if run is done
            if run.status in (RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.STOPPED):
                yield {"event": "done", "data": json.dumps({"status": run.status.value})}
                return

            await asyncio.sleep(0.3)

    return EventSourceResponse(event_generator())


# --- Helpers ---


async def _run_agent(run: AgentRun, orchestrator: AgentOrchestrator) -> None:
    """Background task that executes the agent."""
    await orchestrator.execute(run)


def _to_response(run: AgentRun) -> AgentRunResponse:
    return AgentRunResponse(
        id=run.id,
        domain_id=run.domain_id,
        prompt=run.prompt,
        status=run.status.value,
        events=[
            AgentEventResponse(
                id=e.id,
                timestamp=e.timestamp.isoformat(),
                event_type=e.event_type,
                data=e.data,
            )
            for e in run.events[-50:]  # Last 50 events only
        ],
        started_at=run.started_at.isoformat() if run.started_at else None,
        completed_at=run.completed_at.isoformat() if run.completed_at else None,
        total_cost_usd=run.result.total_cost_usd if run.result else None,
        num_turns=run.result.num_turns if run.result else 0,
        error=run.error,
    )
