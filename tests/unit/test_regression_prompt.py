"""Regression generation prompt content."""

from dojo.core.task import TASK_TYPE_REGISTRY, TaskType


def test_regression_prompt_mentions_artifacts_env_var():
    spec = TASK_TYPE_REGISTRY[TaskType.REGRESSION]
    assert "DOJO_ARTIFACTS_DIR" in spec.generation_prompt_template
