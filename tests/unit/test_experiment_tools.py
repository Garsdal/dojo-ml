"""Unit tests for experiment tool handlers."""

import pytest

from agentml.tools.base import ToolResult
from agentml.tools.experiments import create_experiment_tools


async def test_create_experiment(lab):
    tools = create_experiment_tools(lab)
    create_tool = next(t for t in tools if t.name == "create_experiment")

    result = await create_tool.handler(
        {
            "task_id": "test-task",
            "hypothesis": "Test hypothesis",
        }
    )

    assert isinstance(result, ToolResult)
    assert not result.is_error
    assert "experiment_id" in result.data
    assert result.data["status"] == "running"


async def test_create_experiment_with_variables(lab):
    tools = create_experiment_tools(lab)
    create_tool = next(t for t in tools if t.name == "create_experiment")

    result = await create_tool.handler(
        {
            "task_id": "test-task",
            "hypothesis": "LR outperforms DT",
            "variables": {"model": "linear_regression"},
            "config": {"seed": 42},
        }
    )

    assert not result.is_error
    exp_id = result.data["experiment_id"]

    get_tool = next(t for t in tools if t.name == "get_experiment")
    detail = await get_tool.handler({"experiment_id": exp_id})
    assert detail.data["variables"] == {"model": "linear_regression"}
    assert detail.data["config"] == {"seed": 42}


async def test_complete_experiment(lab):
    tools = create_experiment_tools(lab)
    create_tool = next(t for t in tools if t.name == "create_experiment")
    complete_tool = next(t for t in tools if t.name == "complete_experiment")

    created = await create_tool.handler(
        {
            "task_id": "test-task",
            "hypothesis": "Test",
        }
    )
    exp_id = created.data["experiment_id"]

    result = await complete_tool.handler(
        {
            "experiment_id": exp_id,
            "metrics": {"rmse": 4.2, "r2": 0.87},
            "logs": ["Training complete"],
        }
    )

    assert not result.is_error
    assert result.data["status"] == "completed"
    assert result.data["metrics"]["rmse"] == pytest.approx(4.2)


async def test_complete_experiment_not_found(lab):
    tools = create_experiment_tools(lab)
    complete_tool = next(t for t in tools if t.name == "complete_experiment")

    result = await complete_tool.handler(
        {
            "experiment_id": "nonexistent",
        }
    )

    assert result.is_error
    assert "not found" in result.error.lower()


async def test_fail_experiment(lab):
    tools = create_experiment_tools(lab)
    create_tool = next(t for t in tools if t.name == "create_experiment")
    fail_tool = next(t for t in tools if t.name == "fail_experiment")

    created = await create_tool.handler(
        {
            "task_id": "test-task",
            "hypothesis": "Will fail",
        }
    )
    exp_id = created.data["experiment_id"]

    result = await fail_tool.handler(
        {
            "experiment_id": exp_id,
            "error": "OOM error",
        }
    )

    assert not result.is_error
    assert result.data["status"] == "failed"


async def test_fail_experiment_not_found(lab):
    tools = create_experiment_tools(lab)
    fail_tool = next(t for t in tools if t.name == "fail_experiment")

    result = await fail_tool.handler(
        {
            "experiment_id": "nonexistent",
            "error": "OOM",
        }
    )

    assert result.is_error


async def test_get_experiment(lab):
    tools = create_experiment_tools(lab)
    create_tool = next(t for t in tools if t.name == "create_experiment")
    get_tool = next(t for t in tools if t.name == "get_experiment")

    created = await create_tool.handler(
        {
            "task_id": "test-task",
            "hypothesis": "Test hypothesis",
        }
    )
    exp_id = created.data["experiment_id"]

    result = await get_tool.handler({"experiment_id": exp_id})

    assert not result.is_error
    assert result.data["id"] == exp_id
    assert result.data["task_id"] == "test-task"
    assert result.data["state"] == "running"
    assert result.data["hypothesis"] == "Test hypothesis"


async def test_get_experiment_not_found(lab):
    tools = create_experiment_tools(lab)
    get_tool = next(t for t in tools if t.name == "get_experiment")

    result = await get_tool.handler({"experiment_id": "nonexistent"})

    assert result.is_error


async def test_list_experiments(lab):
    tools = create_experiment_tools(lab)
    create_tool = next(t for t in tools if t.name == "create_experiment")
    list_tool = next(t for t in tools if t.name == "list_experiments")

    await create_tool.handler(
        {
            "task_id": "task-a",
            "hypothesis": "H1",
        }
    )
    await create_tool.handler(
        {
            "task_id": "task-a",
            "hypothesis": "H2",
        }
    )
    await create_tool.handler(
        {
            "task_id": "task-b",
            "hypothesis": "H3",
        }
    )

    # List all
    all_result = await list_tool.handler({})
    assert len(all_result.data) == 3

    # Filter by task
    filtered = await list_tool.handler({"task_id": "task-a"})
    assert len(filtered.data) == 2


async def test_compare_experiments(lab):
    tools = create_experiment_tools(lab)
    create_tool = next(t for t in tools if t.name == "create_experiment")
    complete_tool = next(t for t in tools if t.name == "complete_experiment")
    compare_tool = next(t for t in tools if t.name == "compare_experiments")

    ids = []
    for i, hyp in enumerate(["Try LR", "Try DT"]):
        created = await create_tool.handler(
            {
                "task_id": "task-cmp",
                "hypothesis": hyp,
            }
        )
        exp_id = created.data["experiment_id"]
        ids.append(exp_id)
        await complete_tool.handler(
            {
                "experiment_id": exp_id,
                "metrics": {"rmse": 4.0 + i},
            }
        )

    result = await compare_tool.handler({"experiment_ids": ids})
    assert not result.is_error
    assert result.data["count"] == 2
    assert len(result.data["comparison"]) == 2
    assert result.data["comparison"][0]["hypothesis"] == "Try LR"
    assert result.data["comparison"][1]["hypothesis"] == "Try DT"


async def test_tool_definitions_count(lab):
    tools = create_experiment_tools(lab)
    assert len(tools) == 6
    names = {t.name for t in tools}
    assert names == {
        "create_experiment",
        "complete_experiment",
        "fail_experiment",
        "get_experiment",
        "list_experiments",
        "compare_experiments",
    }
