"""Unit tests for ToolDef, ToolResult, and ToolRegistry."""

import json

import pytest

from agentml.tools.base import ToolDef, ToolRegistry, ToolResult


class TestToolResult:
    def test_data_result_not_error(self):
        r = ToolResult(data={"key": "value"})
        assert not r.is_error
        assert r.data == {"key": "value"}
        assert r.error is None

    def test_error_result(self):
        r = ToolResult(error="something broke")
        assert r.is_error
        assert r.error == "something broke"
        assert r.data is None

    def test_to_text_data(self):
        r = ToolResult(data={"count": 3})
        text = r.to_text()
        parsed = json.loads(text)
        assert parsed == {"count": 3}

    def test_to_text_error(self):
        r = ToolResult(error="not found")
        text = r.to_text()
        parsed = json.loads(text)
        assert parsed == {"error": "not found"}

    def test_to_text_list_data(self):
        r = ToolResult(data=[1, 2, 3])
        text = r.to_text()
        parsed = json.loads(text)
        assert parsed == [1, 2, 3]

    def test_to_text_none_data(self):
        r = ToolResult(data=None)
        text = r.to_text()
        assert text == "null"

    def test_frozen(self):
        r = ToolResult(data="immutable")
        with pytest.raises(AttributeError):
            r.data = "changed"  # type: ignore[misc]


class TestToolDef:
    def test_creation(self):
        async def handler(args):
            return ToolResult(data="ok")

        td = ToolDef(
            name="test_tool",
            description="A test tool",
            parameters={"type": "object", "properties": {}},
            handler=handler,
        )
        assert td.name == "test_tool"
        assert td.description == "A test tool"
        assert td.handler is handler

    def test_frozen(self):
        async def handler(args):
            return ToolResult(data="ok")

        td = ToolDef(
            name="test",
            description="test",
            parameters={},
            handler=handler,
        )
        with pytest.raises(AttributeError):
            td.name = "changed"  # type: ignore[misc]


class TestToolRegistry:
    def test_register_single(self):
        async def handler(args):
            return ToolResult(data="ok")

        reg = ToolRegistry()
        td = ToolDef(name="t1", description="d1", parameters={}, handler=handler)
        reg.register(td)
        assert len(reg.tools) == 1
        assert reg.tool_names == ["t1"]

    def test_register_all(self):
        async def handler(args):
            return ToolResult(data="ok")

        reg = ToolRegistry()
        tools = [
            ToolDef(name=f"t{i}", description=f"d{i}", parameters={}, handler=handler)
            for i in range(3)
        ]
        reg.register_all(tools)
        assert len(reg.tools) == 3
        assert reg.tool_names == ["t0", "t1", "t2"]

    def test_tools_returns_copy(self):
        reg = ToolRegistry()
        tools_a = reg.tools
        tools_b = reg.tools
        assert tools_a is not tools_b
