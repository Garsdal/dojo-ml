"""Dojo.ml experiment management tools."""

import json
from datetime import UTC, datetime
from typing import Any

from dojo.core.experiment import CodeRun, Experiment, ExperimentResult, Hypothesis
from dojo.core.state_machine import ExperimentState
from dojo.runtime.experiment_service import ExperimentService
from dojo.runtime.lab import LabEnvironment
from dojo.tools.base import ToolDef, ToolResult


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

        metrics = args.get("metrics", {}) or {}

        # Phase 3 contract: only metric keys that match the task's expected
        # set are accepted. The agent must call `evaluate` and pass through
        # the dict it returned — it cannot smuggle in custom metrics.
        if exp.domain_id and metrics:
            domain = await lab.domain_store.load(exp.domain_id)
            if domain and domain.task and domain.task.config.get("expected_metrics"):
                expected = set(domain.task.config["expected_metrics"])
                provided = set(metrics)
                extras = provided - expected
                if extras:
                    return ToolResult(
                        error=(
                            f"complete_experiment received metric keys "
                            f"{sorted(extras)} that are not in the task contract "
                            f"({sorted(expected)}). Call the frozen `evaluate` "
                            f"tool and pass through the dict it returns."
                        )
                    )

        exp.result = exp.result or ExperimentResult()
        exp.result.metrics = metrics
        exp.result.logs = args.get("logs", [])
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

    async def run_experiment_code(args: dict[str, Any]) -> ToolResult:
        """Execute Python code for an experiment, storing it as a traceable artifact."""
        experiment_id = args["experiment_id"]
        code = args["code"]
        description = args.get("description", "")

        exp = await service.get(experiment_id)
        if exp is None:
            return ToolResult(error=f"Experiment {experiment_id} not found")
        if exp.state != ExperimentState.RUNNING:
            return ToolResult(
                error=f"Experiment {experiment_id} is not in RUNNING state (state={exp.state.value})"
            )

        # Determine run number
        current_runs = exp.result.code_runs if exp.result else []
        run_number = len(current_runs) + 1

        # Store code as artifact before execution
        code_path = f"experiments/{experiment_id}/run_{run_number}.py"
        await lab.artifact_store.save(code_path, code.encode())

        # Get workspace config from domain
        cwd: str | None = None
        python_path: str | None = None
        env_vars: dict[str, str] | None = None

        if exp.domain_id:
            domain = await lab.domain_store.load(exp.domain_id)
            if domain and domain.workspace and domain.workspace.ready:
                ws = domain.workspace
                cwd = ws.path or None
                python_path = ws.python_path
                env_vars = ws.env_vars or None

        # Execute the code
        exec_result = await lab.sandbox.execute(
            code,
            cwd=cwd,
            python_path=python_path,
            env_vars=env_vars,
        )

        # Store execution metadata
        meta = {
            "run_number": run_number,
            "code_path": code_path,
            "description": description,
            "exit_code": exec_result.exit_code,
            "duration_ms": exec_result.duration_ms,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        meta_path = f"experiments/{experiment_id}/run_{run_number}_meta.json"
        await lab.artifact_store.save(meta_path, json.dumps(meta).encode())

        # Record the code run on the experiment
        code_run = CodeRun(
            run_number=run_number,
            code_path=code_path,
            description=description,
            exit_code=exec_result.exit_code,
            duration_ms=exec_result.duration_ms,
            timestamp=datetime.now(UTC),
        )
        if exp.result is None:
            exp.result = ExperimentResult()
        exp.result.code_runs.append(code_run)
        await lab.experiment_store.save(exp)

        return ToolResult(
            data={
                "exit_code": exec_result.exit_code,
                "stdout": exec_result.stdout,
                "stderr": exec_result.stderr,
                "duration_ms": exec_result.duration_ms,
                "code_path": code_path,
                "run_number": run_number,
            }
        )

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
        ToolDef(
            name="run_experiment_code",
            description=(
                "Execute Python code for an experiment in the workspace environment. "
                "The code is automatically saved as a traceable artifact linked to the experiment. "
                "Use this instead of Bash for all experiment code — it runs with the correct "
                "workspace dependencies (no setup needed) and gives you full code traceability."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "experiment_id": {
                        "type": "string",
                        "description": "The experiment ID this code belongs to",
                    },
                    "code": {
                        "type": "string",
                        "description": "Python code to execute",
                    },
                    "description": {
                        "type": "string",
                        "description": "Brief description of what this code does",
                    },
                },
                "required": ["experiment_id", "code"],
            },
            handler=run_experiment_code,
        ),
    ]
