"""System prompt content — tests for the runtime agent prompt."""

from dojo.agents.prompts import build_system_prompt
from dojo.agents.types import AgentRun
from dojo.core.domain import Domain
from dojo.core.task import Direction, Task, TaskType


def test_system_prompt_documents_artifacts_dir_for_train():
    domain = Domain(
        name="cal_housing",
        prompt="## Goal\npredict prices\n",
        task=Task(
            type=TaskType.REGRESSION,
            primary_metric="rmse",
            direction=Direction.MINIMIZE,
            frozen=True,
            config={"contract_version": 4, "expected_metrics": ["rmse", "r2", "mae"]},
        ),
    )
    run = AgentRun(domain_id="d1", prompt="go")
    out = build_system_prompt(run, domain=domain)
    # Train signature includes artifacts_dir as keyword-only
    assert "def train(X_train, y_train, X_test, *, artifacts_dir)" in out
    # Artifacts section explains the policy
    assert "Artifacts" in out
    assert "evaluate" in out.lower() and "artifacts_dir" in out
    # The framework's evaluate call also threads artifacts_dir
    assert "artifacts_dir=artifacts_dir," in out
    # Mentions train artifacts are opportunistic
    assert "opportunistic" in out.lower() or "discretion" in out.lower()
    # Old, contradictory signature must NOT appear
    assert "def train(X_train, y_train, X_test):" not in out
    assert "def train(X_train, y_train, X_test) -> y_pred" not in out
