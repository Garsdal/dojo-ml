"""Tests for AI-assisted tool generation."""

import pytest

from agentml.core.domain import Domain, DomainTool, ToolType
from agentml.tools.tool_generation import (
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
    domain = Domain(
        name="Test",
        description="Testing",
        tools=[
            DomainTool(name="load_data", description="Load data", type=ToolType.DATA_LOADER),
        ],
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
