"""TaskTypeSpec exposes runner_callsite, verifier_fixture_keys, contract_version."""

from dojo.core.task import TASK_TYPE_REGISTRY, TaskType


def test_regression_spec_has_runner_callsite_using_evaluate_train():
    spec = TASK_TYPE_REGISTRY[TaskType.REGRESSION]
    assert "evaluate(" in spec.runner_callsite
    assert "train(" in spec.runner_callsite


def test_regression_spec_has_verifier_fixture_keys_for_evaluate():
    spec = TASK_TYPE_REGISTRY[TaskType.REGRESSION]
    assert "evaluate" in spec.verifier_fixture_keys
    assert "y_pred" in spec.verifier_fixture_keys["evaluate"]


def test_regression_spec_has_contract_version():
    spec = TASK_TYPE_REGISTRY[TaskType.REGRESSION]
    assert isinstance(spec.contract_version, int)
    assert spec.contract_version >= 1
