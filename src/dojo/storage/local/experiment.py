"""Local experiment store — JSON file per experiment."""

import json
from datetime import datetime
from pathlib import Path

from dojo.core.experiment import CodeRun, Experiment, ExperimentResult, Hypothesis
from dojo.core.state_machine import ExperimentState
from dojo.interfaces.experiment_store import ExperimentStore
from dojo.utils.serialization import to_json


class LocalExperimentStore(ExperimentStore):
    """Persists experiments as JSON files in a local directory."""

    def __init__(self, base_dir: Path | None = None) -> None:
        self.base_dir = base_dir or Path(".dojo/experiments")
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, experiment_id: str) -> Path:
        return self.base_dir / f"{experiment_id}.json"

    async def save(self, experiment: Experiment) -> str:
        """Save experiment as JSON file."""
        self._path(experiment.id).write_text(to_json(experiment))
        return experiment.id

    async def load(self, experiment_id: str) -> Experiment | None:
        """Load experiment from JSON file."""
        path = self._path(experiment_id)
        if not path.exists():
            return None

        data = json.loads(path.read_text())
        return self._from_dict(data)

    async def list(self, *, domain_id: str | None = None) -> list[Experiment]:
        """List all experiments, optionally filtered by domain ID."""
        experiments = []
        for path in self.base_dir.glob("*.json"):
            data = json.loads(path.read_text())
            exp = self._from_dict(data)
            if domain_id is None or exp.domain_id == domain_id:
                experiments.append(exp)
        return experiments

    async def delete(self, experiment_id: str) -> bool:
        """Delete an experiment JSON file."""
        path = self._path(experiment_id)
        if path.exists():
            path.unlink()
            return True
        return False

    @staticmethod
    def _from_dict(data: dict) -> Experiment:
        """Reconstruct an Experiment from a dictionary."""
        hypothesis = None
        if data.get("hypothesis"):
            hypothesis = Hypothesis(**data["hypothesis"])

        result = None
        if data.get("result"):
            result_data = dict(data["result"])
            code_runs_data = result_data.pop("code_runs", [])
            code_runs = [
                CodeRun(
                    run_number=cr.get("run_number", 0),
                    code_path=cr.get("code_path", ""),
                    description=cr.get("description", ""),
                    exit_code=cr.get("exit_code", 0),
                    duration_ms=cr.get("duration_ms", 0.0),
                    timestamp=datetime.fromisoformat(cr["timestamp"])
                    if "timestamp" in cr
                    else datetime.now(),
                    artifact_paths=cr.get("artifact_paths", []),
                )
                for cr in code_runs_data
            ]
            result = ExperimentResult(**result_data, code_runs=code_runs)

        return Experiment(
            id=data["id"],
            domain_id=data.get("domain_id", data.get("task_id", "")),
            hypothesis=hypothesis,
            config=data.get("config", {}),
            state=ExperimentState(data["state"]),
            result=result,
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
        )
