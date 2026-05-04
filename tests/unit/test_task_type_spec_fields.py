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


def test_regression_evaluate_contract_includes_train_test_splits():
    spec = TASK_TYPE_REGISTRY[TaskType.REGRESSION]
    evaluate = next(c for c in spec.required_tools if c.name == "evaluate")
    for key in ["y_pred", "X_train", "X_test", "y_train", "y_test"]:
        assert key in evaluate.params_schema, evaluate.params_schema


def test_regression_runner_callsite_passes_data_to_train_and_evaluate():
    spec = TASK_TYPE_REGISTRY[TaskType.REGRESSION]
    callsite = spec.runner_callsite
    assert "train(X_train, y_train, X_test)" in callsite
    assert "X_train=X_train" in callsite
    assert "y_test=y_test" in callsite


def test_regression_verifier_fixture_keys_cover_extended_evaluate_params():
    spec = TASK_TYPE_REGISTRY[TaskType.REGRESSION]
    keys = spec.verifier_fixture_keys["evaluate"]
    for param in ["y_pred", "X_train", "X_test", "y_train", "y_test"]:
        assert param in keys
    assert keys["y_pred"] == "y_test"
    assert keys["X_train"] == "X_train"


def test_regression_prompt_specifies_new_evaluate_signature():
    spec = TASK_TYPE_REGISTRY[TaskType.REGRESSION]
    prompt = spec.generation_prompt_template
    assert "def evaluate(y_pred, *, X_train, X_test, y_train, y_test)" in prompt
    assert "def evaluate(y_pred):" not in prompt


def test_regression_prompt_describes_train_signature():
    spec = TASK_TYPE_REGISTRY[TaskType.REGRESSION]
    prompt = spec.generation_prompt_template
    assert "train(X_train, y_train, X_test)" in prompt
