"""Experiments router — query experiments."""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from agentml.runtime.lab import LabEnvironment

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
