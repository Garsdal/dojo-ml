"""Unit tests for tracking tool handlers."""

from agentml.tools.base import ToolResult
from agentml.tools.tracking import create_tracking_tools


async def test_log_metrics(lab):
    tools = create_tracking_tools(lab)
    log_tool = next(t for t in tools if t.name == "log_metrics")

    result = await log_tool.handler(
        {
            "experiment_id": "exp-001",
            "metrics": {"accuracy": 0.95, "loss": 0.05},
        }
    )

    assert isinstance(result, ToolResult)
    assert not result.is_error
    assert result.data["status"] == "logged"
    assert result.data["experiment_id"] == "exp-001"

    # Verify metrics were actually persisted
    stored = await lab.tracking.get_metrics("exp-001")
    assert stored["accuracy"] == 0.95
    assert stored["loss"] == 0.05


async def test_log_params(lab):
    tools = create_tracking_tools(lab)
    log_tool = next(t for t in tools if t.name == "log_params")

    result = await log_tool.handler(
        {
            "experiment_id": "exp-002",
            "params": {"learning_rate": 0.01, "epochs": 100},
        }
    )

    assert not result.is_error
    assert result.data["status"] == "logged"
    assert result.data["experiment_id"] == "exp-002"


async def test_tool_definitions_count(lab):
    tools = create_tracking_tools(lab)
    assert len(tools) == 2
    names = {t.name for t in tools}
    assert names == {"log_metrics", "log_params"}
