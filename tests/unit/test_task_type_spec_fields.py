"""TaskTypeSpec exposes runner_callsite, verifier_script, contract_version."""

from dojo.core.task import TASK_TYPE_REGISTRY, TaskType


def test_regression_spec_has_runner_callsite_using_evaluate_train():
    spec = TASK_TYPE_REGISTRY[TaskType.REGRESSION]
    assert "evaluate(" in spec.runner_callsite
    assert "train(" in spec.runner_callsite


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


def test_regression_prompt_specifies_new_evaluate_signature():
    spec = TASK_TYPE_REGISTRY[TaskType.REGRESSION]
    prompt = spec.generation_prompt_template
    assert "def evaluate(y_pred, *, X_train, X_test, y_train, y_test)" in prompt
    assert "def evaluate(y_pred):" not in prompt


def test_regression_prompt_describes_train_signature():
    spec = TASK_TYPE_REGISTRY[TaskType.REGRESSION]
    prompt = spec.generation_prompt_template
    assert "train(X_train, y_train, X_test)" in prompt


def test_regression_spec_runner_prelude_imports_load_data():
    spec = TASK_TYPE_REGISTRY[TaskType.REGRESSION]
    assert "from load_data import load_data" in spec.runner_prelude
    assert "X_train, X_test, y_train, y_test = load_data()" in spec.runner_prelude


def test_regression_spec_has_verifier_script():
    spec = TASK_TYPE_REGISTRY[TaskType.REGRESSION]
    assert "load_data" in spec.verifier_script
    assert "evaluate" in spec.verifier_script
    assert "__DOJO_TOOL_RESULT__" in spec.verifier_script
    assert "__DOJO_TOOL_ERROR__" in spec.verifier_script
