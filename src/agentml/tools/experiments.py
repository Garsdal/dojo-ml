"""AgentML experiment management tools."""

from typing import Any

from agentml.core.experiment import Experiment, ExperimentResult, Hypothesis
from agentml.runtime.experiment_service import ExperimentService
from agentml.runtime.lab import LabEnvironment
from agentml.tools.base import ToolDef, ToolResult


def create_experiment_tools(lab: LabEnvironment) -> list[ToolDef]:
    """Create all experiment tools backed by a LabEnvironment."""
    service = ExperimentService(lab)

    async def create_experiment(args: dict[str, Any]) -> ToolResult:
        exp = Experiment(
            domain_id=args["domain_id"],
            hypothesis=Hypothesis(
                description=args["hypothesis"],
                variables=args.get("variables", {}),
            ),
            config=args.get("config", {}),
        )
        exp_id = await service.create(exp)
        await service.run(exp_id)
        return ToolResult(data={"experiment_id": exp_id, "status": "running"})

    async def complete_experiment(args: dict[str, Any]) -> ToolResult:
        exp = await service.get(args["experiment_id"])
        if exp is None:
            return ToolResult(error=f"Experiment {args['experiment_id']} not found")
        exp.result = ExperimentResult(
            metrics=args.get("metrics", {}),
            logs=args.get("logs", []),
        )
        await service.complete(exp)
        return ToolResult(
            data={
                "experiment_id": exp.id,
                "status": "completed",
                "metrics": exp.result.metrics,
            }
        )

    async def fail_experiment(args: dict[str, Any]) -> ToolResult:
        exp = await service.get(args["experiment_id"])
        if exp is None:
            return ToolResult(error=f"Experiment {args['experiment_id']} not found")
        await service.fail(exp, args["error"])
        return ToolResult(data={"experiment_id": exp.id, "status": "failed"})

    async def get_experiment(args: dict[str, Any]) -> ToolResult:
        exp = await service.get(args["experiment_id"])
        if exp is None:
            return ToolResult(error="Not found")
        return ToolResult(
            data={
                "id": exp.id,
                "domain_id": exp.domain_id,
                "state": exp.state.value,
                "hypothesis": exp.hypothesis.description if exp.hypothesis else None,
                "variables": exp.hypothesis.variables if exp.hypothesis else {},
                "config": exp.config,
                "metrics": exp.result.metrics if exp.result else None,
                "logs": exp.result.logs if exp.result else [],
                "error": exp.result.error if exp.result else None,
            }
        )

    async def list_experiments(args: dict[str, Any]) -> ToolResult:
        experiments = await service.list(domain_id=args.get("domain_id"))
        return ToolResult(
            data=[
                {
                    "id": e.id,
                    "state": e.state.value,
                    "hypothesis": e.hypothesis.description if e.hypothesis else None,
                    "metrics": e.result.metrics if e.result else None,
                }
                for e in experiments
            ]
        )

    async def compare_experiments(args: dict[str, Any]) -> ToolResult:
        rows = []
        for eid in args["experiment_ids"]:
            exp = await service.get(eid)
            if exp:
                rows.append(
                    {
                        "id": exp.id,
                        "hypothesis": exp.hypothesis.description if exp.hypothesis else "—",
                        "state": exp.state.value,
                        "metrics": exp.result.metrics if exp.result else {},
                        "config": exp.config,
                    }
                )
        return ToolResult(data={"comparison": rows, "count": len(rows)})

    return [
        ToolDef(
            name="create_experiment",
            description=(
                "Create a new ML experiment with a hypothesis to test. Returns the "
                "experiment ID. Always create an experiment before running code for it."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "domain_id": {
                        "type": "string",
                        "description": "The domain this experiment belongs to",
                    },
                    "hypothesis": {
                        "type": "string",
                        "description": "What you want to test or prove",
                    },
                    "variables": {
                        "type": "object",
                        "description": (
                            "Key variables for the hypothesis (e.g. model type, hyperparams)"
                        ),
                    },
                    "config": {
                        "type": "object",
                        "description": "Experiment configuration metadata",
                    },
                },
                "required": ["domain_id", "hypothesis"],
            },
            handler=create_experiment,
        ),
        ToolDef(
            name="complete_experiment",
            description=(
                "Mark an experiment as completed with its metrics and optional logs. "
                "Call this after your code has run and you have results."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "experiment_id": {"type": "string"},
                    "metrics": {
                        "type": "object",
                        "description": (
                            "Metric name → float value (e.g. {'rmse': 4.2, 'r2': 0.87})"
                        ),
                    },
                    "logs": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional log messages",
                    },
                },
                "required": ["experiment_id"],
            },
            handler=complete_experiment,
        ),
        ToolDef(
            name="fail_experiment",
            description="Mark an experiment as failed with an error message.",
            parameters={
                "type": "object",
                "properties": {
                    "experiment_id": {"type": "string"},
                    "error": {
                        "type": "string",
                        "description": "What went wrong",
                    },
                },
                "required": ["experiment_id", "error"],
            },
            handler=fail_experiment,
        ),
        ToolDef(
            name="get_experiment",
            description=(
                "Get full details of an experiment including its state, "
                "hypothesis, config, and results."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "experiment_id": {
                        "type": "string",
                        "description": "The experiment ID",
                    },
                },
                "required": ["experiment_id"],
            },
            handler=get_experiment,
        ),
        ToolDef(
            name="list_experiments",
            description="List all experiments, optionally filtered by domain ID.",
            parameters={
                "type": "object",
                "properties": {
                    "domain_id": {
                        "type": "string",
                        "description": "Filter by domain ID (optional)",
                    },
                },
            },
            handler=list_experiments,
        ),
        ToolDef(
            name="compare_experiments",
            description=(
                "Compare metrics across multiple experiments side by side. "
                "Use this to evaluate which approach works best."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "experiment_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of experiment IDs to compare",
                    },
                },
                "required": ["experiment_ids"],
            },
            handler=compare_experiments,
        ),
    ]
