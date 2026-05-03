"""Domain tool executor — registers executable domain tools as MCP ToolDefs."""

from __future__ import annotations

import json
import textwrap
from typing import Any

from dojo.core.domain import Domain, DomainTool
from dojo.runtime.lab import LabEnvironment
from dojo.tools.base import ToolDef, ToolResult


def create_domain_tools(lab: LabEnvironment, domain: Domain) -> list[ToolDef]:
    """Create ToolDef entries for all executable domain tools.

    Only tools with executable=True are registered as MCP tools.
    Non-executable tools remain as text hints in the system prompt.

    Args:
        lab: The lab environment (provides sandbox access).
        domain: The domain whose tools to register.

    Returns:
        List of ToolDef entries ready for registration.
    """
    return [
        _make_tool_def(lab, tool, domain) for tool in domain.tools if tool.executable and tool.code
    ]


def _make_tool_def(lab: LabEnvironment, tool: DomainTool, domain: Domain) -> ToolDef:
    """Wrap a domain tool's code as an executable ToolDef."""

    async def handler(args: dict[str, Any]) -> ToolResult:
        return await _execute_domain_tool(lab, tool, domain, args)

    return ToolDef(
        name=tool.name,
        description=_build_description(tool),
        parameters=tool.parameters or {"type": "object", "properties": {}},
        handler=handler,
    )


def _build_description(tool: DomainTool) -> str:
    """Build the tool description including return info."""
    desc = tool.description
    if tool.return_description:
        desc += f" Returns: {tool.return_description}"
    return desc


async def _execute_domain_tool(
    lab: LabEnvironment,
    tool: DomainTool,
    domain: Domain,
    args: dict[str, Any],
) -> ToolResult:
    """Execute a domain tool's code in the workspace context."""
    script = _build_tool_script(tool.code, args)

    cwd: str | None = None
    python_path: str | None = None
    env_vars: dict[str, str] | None = None

    if domain.workspace and domain.workspace.ready:
        ws = domain.workspace
        cwd = ws.path or None
        python_path = ws.python_path
        env_vars = ws.env_vars or None

    result = await lab.sandbox.execute(
        script,
        cwd=cwd,
        python_path=python_path,
        env_vars=env_vars,
    )

    if result.exit_code != 0:
        return ToolResult(
            error=f"Tool '{tool.name}' failed (exit {result.exit_code}): {result.stderr}"
        )

    stdout = result.stdout.strip()
    if not stdout:
        return ToolResult(data={"result": None, "stdout": ""})

    # Try to parse JSON output
    try:
        parsed = json.loads(stdout)
        return ToolResult(data=parsed if isinstance(parsed, dict) else {"result": parsed})
    except json.JSONDecodeError:
        return ToolResult(data={"result": stdout})


def _build_tool_script(code: str, args: dict[str, Any]) -> str:
    """Wrap tool code in a script that injects args and prints JSON result."""
    args_json = json.dumps(args)

    return textwrap.dedent(f"""\
        import json as _json
        import sys as _sys

        # Inject tool arguments as local variables
        _args = _json.loads({args_json!r})
        for _k, _v in _args.items():
            locals()[_k] = _v

        # Execute the tool code
        {textwrap.indent(code, "        ").strip()}
    """)
