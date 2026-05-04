"""_build_fixtures consumes verifier_fixture_keys from TaskTypeSpec."""

from dojo.core.task import TASK_TYPE_REGISTRY, TaskType
from dojo.runtime.tool_verifier import _build_fixtures


def test_build_fixtures_uses_spec_mapping_for_evaluate():
    spec = TASK_TYPE_REGISTRY[TaskType.REGRESSION]
    raw_outputs = {
        "load_data": {
            "X_train": [[1.0]],
            "X_test": [[2.0]],
            "y_train": [1.0],
            "y_test": [2.0],
        }
    }
    fixtures = _build_fixtures(spec, "evaluate", raw_outputs)
    assert fixtures is not None
    assert fixtures["y_pred"] == [2.0]


def test_build_fixtures_returns_none_for_unknown_tool():
    spec = TASK_TYPE_REGISTRY[TaskType.REGRESSION]
    fixtures = _build_fixtures(spec, "nonexistent_tool", {})
    assert fixtures is None


def test_build_fixtures_returns_none_when_upstream_missing():
    spec = TASK_TYPE_REGISTRY[TaskType.REGRESSION]
    fixtures = _build_fixtures(spec, "evaluate", {})  # no load_data outputs
    assert fixtures is None
