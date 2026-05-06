"""Tests for AI-assisted tool generation."""

import pytest

from dojo.core.domain import Domain, DomainTool, ToolType
from dojo.core.task import Task, TaskType
from dojo.tools.tool_generation import (
    build_task_generation_prompt,
    build_tool_generation_prompt,
    dicts_to_domain_tools,
    parse_generated_tools,
)


def test_build_prompt_basic():
    domain = Domain(name="Sentiment Analysis", description="NLP sentiment classification")
    prompt = build_tool_generation_prompt(domain)
    assert "Sentiment Analysis" in prompt
    assert "NLP sentiment classification" in prompt
    assert "JSON array" in prompt


def test_build_prompt_with_hint():
    domain = Domain(name="Test", description="Testing")
    prompt = build_tool_generation_prompt(domain, hint="CSV data loaders")
    assert "CSV data loaders" in prompt


def test_build_prompt_with_existing_tools():
    """Phase 4: existing-tools list is read from domain.task.tools."""
    domain = Domain(
        name="Test",
        description="Testing",
        task=Task(
            tools=[
                DomainTool(name="load_data", description="Load data", type=ToolType.DATA_LOADER),
            ]
        ),
    )
    prompt = build_tool_generation_prompt(domain)
    assert "load_data" in prompt
    assert "Do NOT duplicate" in prompt


def test_parse_generated_tools_json():
    raw = """Here are the generated tools:
```json
[
  {
    "name": "load_csv",
    "description": "Load a CSV file",
    "type": "data_loader",
    "parameters": {"file_path": {"type": "string"}},
    "example_usage": "import pandas as pd\\ndf = pd.read_csv(args['file_path'])"
  }
]
```
"""
    tools = parse_generated_tools(raw)
    assert len(tools) == 1
    assert tools[0]["name"] == "load_csv"
    assert tools[0]["type"] == "data_loader"


def test_parse_generated_tools_bare_json():
    raw = '[{"name": "my_tool", "description": "test", "type": "custom", "example_usage": "", "parameters": {}}]'
    tools = parse_generated_tools(raw)
    assert len(tools) == 1
    assert tools[0]["name"] == "my_tool"


def test_parse_generated_tools_invalid():
    with pytest.raises(ValueError, match="No JSON array"):
        parse_generated_tools("This is not JSON at all")


def test_parse_generated_tools_invalid_json():
    with pytest.raises(ValueError, match="Invalid JSON"):
        parse_generated_tools("[{not valid json}]")


def test_parse_validates_name():
    raw = '[{"description": "no name", "type": "custom", "example_usage": "", "parameters": {}}]'
    with pytest.raises(ValueError, match="'name' is required"):
        parse_generated_tools(raw)


def test_parse_sanitizes_name():
    raw = '[{"name": "My Tool Name!", "description": "test", "type": "custom", "example_usage": "", "parameters": {}}]'
    tools = parse_generated_tools(raw)
    assert tools[0]["name"] == "my_tool_name_"


def test_parse_invalid_type_defaults_to_custom():
    raw = '[{"name": "tool", "description": "test", "type": "invalid_type", "example_usage": "", "parameters": {}}]'
    tools = parse_generated_tools(raw)
    assert tools[0]["type"] == "custom"


def test_dicts_to_domain_tools():
    dicts = [
        {
            "name": "load_data",
            "description": "Load data from file",
            "type": "data_loader",
            "example_usage": "df = pd.read_csv(path)",
            "parameters": {"path": {"type": "string"}},
        }
    ]
    tools = dicts_to_domain_tools(dicts, created_by="ai")
    assert len(tools) == 1
    assert isinstance(tools[0], DomainTool)
    assert tools[0].name == "load_data"
    assert tools[0].type == ToolType.DATA_LOADER
    assert tools[0].created_by == "ai"


def test_parse_multiple_tools():
    raw = """```json
[
  {"name": "loader", "description": "Load", "type": "data_loader", "example_usage": "load()", "parameters": {}},
  {"name": "eval", "description": "Evaluate", "type": "evaluator", "example_usage": "evaluate()", "parameters": {}}
]
```"""
    tools = parse_generated_tools(raw)
    assert len(tools) == 2
    assert tools[0]["name"] == "loader"
    assert tools[1]["name"] == "eval"


# --- Phase 3.5: registry-aware prompt + SETUP.md threading -----------------


def test_build_task_generation_prompt_uses_regression_template():
    """For regression, the registry-specific template is used (not the generic one)."""
    domain = Domain(name="housing", description="predict house prices")
    task = Task(type=TaskType.REGRESSION, config={})
    prompt = build_task_generation_prompt(domain, task)
    # Regression-specific markers — would not appear in the generic prompt
    assert "load_data" in prompt
    assert "evaluate" in prompt
    assert "rmse" in prompt
    assert "r2" in prompt
    assert "mae" in prompt


def test_build_task_generation_prompt_threads_setup_md():
    """Phase 3.5: SETUP.md content is fenced into the prompt as the user's spec."""
    domain = Domain(name="housing", description="d")
    task = Task(type=TaskType.REGRESSION, config={})
    setup = "## Dataset\nUse sklearn.datasets.fetch_california_housing(return_X_y=True).\n"
    prompt = build_task_generation_prompt(domain, task, setup_md=setup)
    assert "SETUP.md" in prompt
    assert "fetch_california_housing" in prompt
    # Empty config fields should signal "use SETUP.md" rather than literal "(unset)"
    assert "use SETUP.md" in prompt


def test_build_task_generation_prompt_handles_empty_setup_md():
    """No SETUP.md means no fenced spec — but the prompt still works."""
    domain = Domain(name="d", description="d")
    task = Task(type=TaskType.REGRESSION, config={"data_path": "/tmp/x.csv"})
    prompt = build_task_generation_prompt(domain, task)  # setup_md default ""
    assert "empty" in prompt
    assert "/tmp/x.csv" in prompt
