"""Regression generation prompt content."""

from dojo.core.task import TASK_TYPE_REGISTRY, TaskType


def test_regression_prompt_mentions_artifacts_dir_parameter():
    spec = TASK_TYPE_REGISTRY[TaskType.REGRESSION]
    assert "artifacts_dir" in spec.generation_prompt_template
    assert "DOJO_ARTIFACTS_DIR" not in spec.generation_prompt_template
