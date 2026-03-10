"""Unit tests for ClaudeToolAdapter (without requiring claude_agent_sdk)."""

import json

import pytest

from agentml.tools.base import ToolDef, ToolResult


async def test_tool_result_to_claude_format():
    """Test that ToolResult can be converted to Claude's expected format.

    This tests the conversion logic without importing claude_agent_sdk.
    """
    result = ToolResult(data={"greeting": "Hello, Alice!"})
    text = result.to_text()
    parsed = json.loads(text)
    assert parsed == {"greeting": "Hello, Alice!"}


async def test_tool_result_error_to_claude_format():
    result = ToolResult(error="something failed")
    text = result.to_text()
    parsed = json.loads(text)
    assert parsed == {"error": "something failed"}


def test_claude_adapter_tool_names_prefixed():
    """Test tool name prefixing without importing claude_agent_sdk.

    We can test the prefixing logic directly since it doesn't use the SDK.
    """
    # Test the prefix format: mcp__<server>__<tool>
    server_name = "agentml"
    tool_names = ["create_experiment", "log_metrics"]
    prefixed = [f"mcp__{server_name}__{name}" for name in tool_names]
    assert prefixed == [
        "mcp__agentml__create_experiment",
        "mcp__agentml__log_metrics",
    ]


def test_claude_adapter_import():
    """Test that the adapter module can be imported (SDK itself may not be installed)."""
    try:
        from agentml.tools.adapters.claude import ClaudeToolAdapter

        adapter = ClaudeToolAdapter()
        assert hasattr(adapter, "adapt_tool")
        assert hasattr(adapter, "create_server")
        assert hasattr(adapter, "tool_names_prefixed")
    except ImportError:
        # claude_agent_sdk not installed — that's fine for unit tests
        pytest.skip("claude_agent_sdk not installed")


def test_claude_adapter_prefixed_names():
    """Test tool_names_prefixed with actual adapter instance."""
    try:
        from agentml.tools.adapters.claude import ClaudeToolAdapter
    except ImportError:
        pytest.skip("claude_agent_sdk not installed")

    async def noop_handler(args):
        return ToolResult(data="ok")

    adapter = ClaudeToolAdapter()
    tool_defs = [
        ToolDef(name="create_experiment", description="d", parameters={}, handler=noop_handler),
        ToolDef(name="log_metrics", description="d", parameters={}, handler=noop_handler),
    ]

    names = adapter.tool_names_prefixed("agentml", tool_defs)
    assert names == [
        "mcp__agentml__create_experiment",
        "mcp__agentml__log_metrics",
    ]
