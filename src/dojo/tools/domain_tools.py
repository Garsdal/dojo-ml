"""Domain tool executor — registers executable domain tools as MCP ToolDefs."""

from __future__ import annotations

import json
from typing import Any

from dojo.core.domain import Domain, DomainTool
from dojo.runtime.lab import LabEnvironment
from dojo.tools.base import ToolDef, ToolResult


def create_domain_tools(lab: LabEnvironment, domain: Domain) -> list[ToolDef]:
    """Create ToolDef entries for all executable tools on a domain.

    Source of truth (Phase 3): `domain.task.tools` when a task is set.
    Falls back to `domain.tools` only when no task exists, for legacy
    domains created before Phase 1.

    Only tools with executable=True are registered as MCP tools.
    Non-executable tools remain as text hints in the system prompt.
    """
    tools = _select_tools(domain)
    return [_make_tool_def(lab, tool, domain) for tool in tools if tool.executable and tool.code]


def _select_tools(domain: Domain) -> list[DomainTool]:
    """Pick which tools the orchestrator should register.

    Prefers `domain.task.tools` when a task is set (Phase 3 contract);
    falls back to `domain.tools` for legacy domains without a task.
    """
    if domain.task is not None and domain.task.tools:
        return list(domain.task.tools)
    return list(domain.tools)


def _make_tool_def(lab: LabEnvironment, tool: DomainTool, domain: Domain) -> ToolDef:
    """Wrap a domain tool's code as an executable ToolDef."""

    async def handler(args: dict[str, Any]) -> ToolResult:
        return await _execute_domain_tool(lab, tool, domain, args)

    return ToolDef(
        name=tool.name,
        description=_build_description(tool),
        parameters=_normalize_params(tool.parameters),
        handler=handler,
    )


def _normalize_params(params: dict[str, Any]) -> dict[str, Any]:
    """Wrap AI-style `{name: schema}` into MCP-style `{type:object, properties:{...}}`.

    AI generators sometimes emit the parameters flat (e.g.
    ``{"y_pred": {"type": "array"}}``). MCP needs a JSON-schema object
    envelope. If `params` already looks like a JSON schema (has "type":
    "object"), pass it through untouched.
    """
    if not params:
        return {"type": "object", "properties": {}}
    if params.get("type") == "object" and "properties" in params:
        return params
    # Flat form — wrap each entry under properties
    return {
        "type": "object",
        "properties": {
            k: v if isinstance(v, dict) else {"type": "string"} for k, v in params.items()
        },
    }


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
        name=tool.name,
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
    """Wrap tool code in a script that injects args as module globals.

    We emit `name = <python-literal>` assignments rather than `locals()[k] = v`,
    which is brittle across scopes (a variable looked up after an `import` or
    inside a comprehension can fail to resolve, depending on Python version).
    """
    assignments = "".join(f"{name} = {value!r}\n" for name, value in args.items())
    return f"# --- injected tool arguments ---\n{assignments}\n# --- tool code ---\n{code}\n"
