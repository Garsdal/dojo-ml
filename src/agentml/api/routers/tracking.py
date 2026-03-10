"""Tracking router — query tracked metrics."""

from fastapi import APIRouter, Request

from agentml.runtime.lab import LabEnvironment

router = APIRouter(prefix="/tracking", tags=["tracking"])


def _get_lab(request: Request) -> LabEnvironment:
    return request.app.state.lab


@router.get("/{experiment_id}/metrics")
async def get_tracked_metrics(experiment_id: str, request: Request) -> dict[str, float]:
    """Get tracked metrics for a specific experiment."""
    lab = _get_lab(request)
    return await lab.tracking.get_metrics(experiment_id)
