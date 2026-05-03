"""Experiments router — query experiments."""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from dojo.runtime.lab import LabEnvironment

router = APIRouter(prefix="/experiments", tags=["experiments"])


def _get_lab(request: Request) -> LabEnvironment:
    return request.app.state.lab


class ExperimentResponse(BaseModel):
    """API response for an experiment."""

    id: str
    domain_id: str
    state: str
    config: dict = {}
    metrics: dict[str, float] | None = None
    error: str | None = None


@router.get("", response_model=list[ExperimentResponse])
async def list_experiments(
    request: Request, domain_id: str | None = None
) -> list[ExperimentResponse]:
    """List all experiments, optionally filtered by domain ID."""
    lab = _get_lab(request)
    experiments = await lab.experiment_store.list(domain_id=domain_id)
    return [
        ExperimentResponse(
            id=exp.id,
            domain_id=exp.domain_id,
            state=exp.state.value,
            config=exp.config,
            metrics=exp.result.metrics if exp.result else None,
            error=exp.result.error if exp.result else None,
        )
        for exp in experiments
    ]


@router.get("/{experiment_id}", response_model=ExperimentResponse)
async def get_experiment(experiment_id: str, request: Request) -> ExperimentResponse:
    """Get a specific experiment by ID."""
    lab = _get_lab(request)
    exp = await lab.experiment_store.load(experiment_id)
    if exp is None:
        raise HTTPException(status_code=404, detail="Experiment not found")

    return ExperimentResponse(
        id=exp.id,
        domain_id=exp.domain_id,
        state=exp.state.value,
        config=exp.config,
        metrics=exp.result.metrics if exp.result else None,
        error=exp.result.error if exp.result else None,
    )


class CodeRunResponse(BaseModel):
    """API response for a code run."""

    run_number: int
    code_path: str
    description: str
    exit_code: int
    duration_ms: float
    timestamp: str


@router.get("/{experiment_id}/code", response_model=list[CodeRunResponse])
async def list_experiment_code_runs(experiment_id: str, request: Request) -> list[CodeRunResponse]:
    """List all code runs for an experiment."""
    lab = _get_lab(request)
    exp = await lab.experiment_store.load(experiment_id)
    if exp is None:
        raise HTTPException(status_code=404, detail="Experiment not found")

    code_runs = exp.result.code_runs if exp.result else []
    return [
        CodeRunResponse(
            run_number=cr.run_number,
            code_path=cr.code_path,
            description=cr.description,
            exit_code=cr.exit_code,
            duration_ms=cr.duration_ms,
            timestamp=cr.timestamp.isoformat(),
        )
        for cr in code_runs
    ]


@router.get("/{experiment_id}/code/{run_number}")
async def get_experiment_code_run(experiment_id: str, run_number: int, request: Request) -> dict:
    """Get a specific code run — returns the code, metadata, and execution result."""
    lab = _get_lab(request)
    exp = await lab.experiment_store.load(experiment_id)
    if exp is None:
        raise HTTPException(status_code=404, detail="Experiment not found")

    code_runs = exp.result.code_runs if exp.result else []
    code_run = next((cr for cr in code_runs if cr.run_number == run_number), None)
    if code_run is None:
        raise HTTPException(status_code=404, detail=f"Code run {run_number} not found")

    # Load code from artifact store
    code_bytes = await lab.artifact_store.load(code_run.code_path)
    code = code_bytes.decode() if code_bytes else ""

    return {
        "run_number": code_run.run_number,
        "code_path": code_run.code_path,
        "description": code_run.description,
        "exit_code": code_run.exit_code,
        "duration_ms": code_run.duration_ms,
        "timestamp": code_run.timestamp.isoformat(),
        "code": code,
    }
