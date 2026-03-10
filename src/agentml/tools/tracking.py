"""AgentML tracking tools."""

from typing import Any

from agentml.runtime.lab import LabEnvironment
from agentml.tools.base import ToolDef, ToolResult


def create_tracking_tools(lab: LabEnvironment) -> list[ToolDef]:
    """Create tracking tools backed by a LabEnvironment."""

    async def log_metrics(args: dict[str, Any]) -> ToolResult:
        await lab.tracking.log_metrics(args["experiment_id"], args["metrics"])
        return ToolResult(data={"status": "logged", "experiment_id": args["experiment_id"]})

    async def log_params(args: dict[str, Any]) -> ToolResult:
        await lab.tracking.log_params(args["experiment_id"], args["params"])
        return ToolResult(data={"status": "logged", "experiment_id": args["experiment_id"]})

    return [
        ToolDef(
            name="log_metrics",
            description=(
                "Log numeric metrics for an experiment to the tracking backend "
                "(MLflow or file). Call this after evaluating a model."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "experiment_id": {"type": "string"},
                    "metrics": {
                        "type": "object",
                        "description": ("Metric name → float value (e.g. {'accuracy': 0.95})"),
                    },
                },
                "required": ["experiment_id", "metrics"],
            },
            handler=log_metrics,
        ),
        ToolDef(
            name="log_params",
            description=(
                "Log parameters/hyperparameters for an experiment to the tracking backend."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "experiment_id": {"type": "string"},
                    "params": {
                        "type": "object",
                        "description": ("Parameter name → value (e.g. {'learning_rate': 0.01})"),
                    },
                },
                "required": ["experiment_id", "params"],
            },
            handler=log_params,
        ),
    ]
