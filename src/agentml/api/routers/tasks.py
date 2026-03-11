"""Tasks router — submit and query tasks (unified with AgentOrchestrator)."""

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from agentml.agents.factory import create_agent_backend
from agentml.agents.orchestrator import AgentOrchestrator
from agentml.core.task import Task, TaskResult, TaskStatus
from agentml.runtime.lab import LabEnvironment

router = APIRouter(prefix="/tasks", tags=["tasks"])

# In-memory task store for PoC (not persistent across restarts)
_tasks: dict[str, Task] = {}


def _get_lab(request: Request) -> LabEnvironment:
    return request.app.state.lab


class CreateTaskRequest(BaseModel):
    """Request body for creating a task."""

    prompt: str


class ExperimentSummary(BaseModel):
    """Summary of an experiment for API responses."""

    id: str
    state: str
    metrics: dict[str, float] | None = None


class TaskResponse(BaseModel):
    """API response for a task."""

    id: str
    prompt: str
    status: str
    summary: str | None = None
    experiments: list[ExperimentSummary] = []
    metrics: dict[str, float] | None = None


@router.post("", response_model=TaskResponse)
async def create_task(body: CreateTaskRequest, request: Request) -> TaskResponse:
    """Create and run a task through the AgentOrchestrator pipeline."""
    lab = _get_lab(request)
    settings = request.app.state.settings

    task = Task(prompt=body.prompt)
    task.status = TaskStatus.RUNNING
    task.updated_at = datetime.now(UTC)

    # Use the same AgentOrchestrator + backend as /agent/run
    backend = create_agent_backend(settings.agent.backend)
    orchestrator = AgentOrchestrator(
        lab,
        backend,
        max_turns=settings.agent.max_turns,
        max_budget_usd=settings.agent.max_budget_usd,
        permission_mode=settings.agent.permission_mode,
        cwd=settings.agent.cwd,
    )

    run = await orchestrator.start(prompt=body.prompt, task_id=task.id)
    await orchestrator.execute(run)

    # Build result from the run's completed state
    best_exp_id: str | None = None
    best_metrics: dict[str, float] = {}

    # Gather experiment summaries created by the tool pipeline
    experiments = await lab.experiment_store.list(domain_id=task.id)
    exp_summaries = [
        ExperimentSummary(
            id=exp.id,
            state=exp.state.value,
            metrics=exp.result.metrics if exp.result else None,
        )
        for exp in experiments
    ]

    if experiments:
        best_exp = experiments[0]
        best_exp_id = best_exp.id
        best_metrics = best_exp.result.metrics if best_exp.result else {}

    task.result = TaskResult(
        summary=f"Agent completed task: {body.prompt}",
        best_experiment_id=best_exp_id,
        metrics=best_metrics,
        details={"experiments_run": len(experiments), "agent_run_id": run.id},
    )
    task.status = TaskStatus.COMPLETED if run.error is None else TaskStatus.FAILED
    task.experiment_ids = [exp.id for exp in experiments]
    task.updated_at = datetime.now(UTC)

    # Store task
    _tasks[task.id] = task

    return TaskResponse(
        id=task.id,
        prompt=task.prompt,
        status=task.status.value,
        summary=task.result.summary,
        experiments=exp_summaries,
        metrics=task.result.metrics,
    )


@router.get("", response_model=list[TaskResponse])
async def list_tasks(request: Request) -> list[TaskResponse]:
    """List all tasks."""
    lab = _get_lab(request)
    responses = []
    for task in _tasks.values():
        experiments = await lab.experiment_store.list(domain_id=task.id)
        exp_summaries = [
            ExperimentSummary(
                id=exp.id,
                state=exp.state.value,
                metrics=exp.result.metrics if exp.result else None,
            )
            for exp in experiments
        ]
        responses.append(
            TaskResponse(
                id=task.id,
                prompt=task.prompt,
                status=task.status.value,
                summary=task.result.summary if task.result else None,
                experiments=exp_summaries,
                metrics=task.result.metrics if task.result else None,
            )
        )
    return responses


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(task_id: str, request: Request) -> TaskResponse:
    """Get a specific task by ID."""
    lab = _get_lab(request)

    task = _tasks.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    experiments = await lab.experiment_store.list(domain_id=task.id)
    exp_summaries = [
        ExperimentSummary(
            id=exp.id,
            state=exp.state.value,
            metrics=exp.result.metrics if exp.result else None,
        )
        for exp in experiments
    ]

    return TaskResponse(
        id=task.id,
        prompt=task.prompt,
        status=task.status.value,
        summary=task.result.summary if task.result else None,
        experiments=exp_summaries,
        metrics=task.result.metrics if task.result else None,
    )
