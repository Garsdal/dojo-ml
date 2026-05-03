"""Tests for executable domain tools."""

from pathlib import Path

from dojo.core.domain import Domain, DomainTool, Workspace, WorkspaceSource
from dojo.tools.domain_tools import _build_tool_script, create_domain_tools


def test_create_domain_tools_skips_non_executable(lab):
    """Only executable tools become ToolDefs."""
    domain = Domain(
        name="Test",
        tools=[
            DomainTool(name="hint_tool", description="A hint", executable=False),
            DomainTool(
                name="exec_tool",
                description="Executable",
                executable=True,
                code="print('hi')",
            ),
        ],
    )
    tools = create_domain_tools(lab, domain)
    assert len(tools) == 1
    assert tools[0].name == "exec_tool"


def test_create_domain_tools_empty(lab):
    """Domain with no executable tools returns empty list."""
    domain = Domain(name="Test", tools=[])
    tools = create_domain_tools(lab, domain)
    assert tools == []


def test_create_domain_tools_skips_no_code(lab):
    """Executable=True but no code is skipped."""
    domain = Domain(
        name="Test",
        tools=[DomainTool(name="nocode", executable=True, code="")],
    )
    tools = create_domain_tools(lab, domain)
    assert tools == []


async def test_executable_tool_runs_code(lab):
    """Executable domain tool runs code and returns JSON output."""
    domain = Domain(
        name="Test",
        tools=[
            DomainTool(
                name="get_answer",
                description="Returns the answer to everything",
                executable=True,
                code='import json\nprint(json.dumps({"answer": 42}))',
            )
        ],
    )
    tools = {t.name: t for t in create_domain_tools(lab, domain)}
    assert "get_answer" in tools

    result = await tools["get_answer"].handler({})
    assert result.error is None
    assert result.data["answer"] == 42


async def test_executable_tool_uses_workspace(lab, tmp_path: Path):
    """Executable tool uses workspace cwd when workspace is ready."""
    # Create workspace
    (tmp_path / "data.txt").write_text("hello from workspace")
    domain = Domain(
        name="Test",
        workspace=Workspace(source=WorkspaceSource.LOCAL, path=str(tmp_path), ready=True),
        tools=[
            DomainTool(
                name="read_data",
                description="Read data.txt",
                executable=True,
                code='import json\ncontent = open("data.txt").read()\nprint(json.dumps({"content": content}))',
            )
        ],
    )
    tools = {t.name: t for t in create_domain_tools(lab, domain)}
    result = await tools["read_data"].handler({})
    assert result.error is None
    assert result.data["content"] == "hello from workspace"


def test_build_tool_script_injects_args():
    """_build_tool_script emits direct assignments so vars survive imports/scoping."""
    script = _build_tool_script("x = name\nprint(x)", {"name": "test_value"})
    assert "name = 'test_value'" in script
    assert "x = name" in script
    assert script.index("name = 'test_value'") < script.index("x = name")


async def test_executable_tool_error_on_failure(lab):
    """Executable tool returns error on non-zero exit code."""
    domain = Domain(
        name="Test",
        tools=[
            DomainTool(
                name="failing_tool",
                description="Always fails",
                executable=True,
                code="import sys\nsys.exit(1)",
            )
        ],
    )
    tools = {t.name: t for t in create_domain_tools(lab, domain)}
    result = await tools["failing_tool"].handler({})
    assert result.error is not None
    assert "failing_tool" in result.error


def test_create_domain_tools_multiple_executable(lab):
    """All executable tools with code are registered."""
    domain = Domain(
        name="Test",
        tools=[
            DomainTool(name="tool_a", executable=True, code="print('a')"),
            DomainTool(name="tool_b", executable=True, code="print('b')"),
            DomainTool(name="tool_c", executable=False),
        ],
    )
    tools = create_domain_tools(lab, domain)
    names = {t.name for t in tools}
    assert names == {"tool_a", "tool_b"}


async def test_executable_tool_non_json_stdout(lab):
    """Tool that prints non-JSON stdout returns it under 'result' key."""
    domain = Domain(
        name="Test",
        tools=[
            DomainTool(
                name="plain_output",
                description="Prints plain text",
                executable=True,
                code="print('just plain text')",
            )
        ],
    )
    tools = {t.name: t for t in create_domain_tools(lab, domain)}
    result = await tools["plain_output"].handler({})
    assert result.error is None
    assert result.data["result"] == "just plain text"


async def test_executable_tool_no_stdout(lab):
    """Tool that produces no stdout returns result=None."""
    domain = Domain(
        name="Test",
        tools=[
            DomainTool(
                name="silent_tool",
                description="Produces no output",
                executable=True,
                code="x = 1 + 1",
            )
        ],
    )
    tools = {t.name: t for t in create_domain_tools(lab, domain)}
    result = await tools["silent_tool"].handler({})
    assert result.error is None
    assert result.data == {"result": None, "stdout": ""}


def test_build_tool_script_empty_args():
    """_build_tool_script handles empty args dict."""
    script = _build_tool_script("print('hello')", {})
    assert "print('hello')" in script
    # No phantom assignments when there's nothing to inject
    assert "= " not in script.split("# --- tool code ---")[0]


def test_tool_def_description_includes_return_description(lab):
    """Tool description is extended with return_description when set."""
    domain = Domain(
        name="Test",
        tools=[
            DomainTool(
                name="described_tool",
                description="Does something.",
                executable=True,
                code="print('x')",
                return_description="The result value.",
            )
        ],
    )
    tools = create_domain_tools(lab, domain)
    assert len(tools) == 1
    assert "The result value." in tools[0].description


def test_tool_def_description_without_return_description(lab):
    """Tool description is unchanged when return_description is empty."""
    domain = Domain(
        name="Test",
        tools=[
            DomainTool(
                name="no_return_desc",
                description="Does something.",
                executable=True,
                code="print('x')",
                return_description="",
            )
        ],
    )
    tools = create_domain_tools(lab, domain)
    assert tools[0].description == "Does something."
