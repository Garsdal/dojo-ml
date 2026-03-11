"""Dynamic tool registration from domain tool definitions.

Converts DomainTool instances (with executable code) into ToolDef entries
that can be injected into an agent's available tools at run time.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from agentml.core.domain import DomainTool
from agentml.tools.base import ToolDef, ToolResult
from agentml.utils.logging import get_logger

logger = get_logger(__name__)

# Default timeout for domain tool execution (seconds)
_TOOL_TIMEOUT = 30


def domain_tools_to_tooldefs(domain_tools: list[DomainTool]) -> list[ToolDef]:
    """Convert domain-specific tool definitions into ToolDef instances.

    Each DomainTool's code is wrapped in a sandbox-style executor that
    writes the code to a temp file and runs it as a subprocess.
    """
    return [_create_tooldef(tool) for tool in domain_tools]


def _create_tooldef(tool: DomainTool) -> ToolDef:
    """Create a single ToolDef from a DomainTool."""

    async def handler(args: dict[str, Any]) -> ToolResult:
        """Execute domain tool code in a subprocess."""
        try:
            # Write the tool code + invocation to a temp file
            with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
                # The code may define functions. We inject the args as JSON
                # and call a main() function or execute the code directly.
                script = _build_script(tool.code, args)
                f.write(script)
                f.flush()
                script_path = Path(f.name)

            try:
                result = subprocess.run(
                    ["python", str(script_path)],
                    capture_output=True,
                    text=True,
                    timeout=_TOOL_TIMEOUT,
                )

                if result.returncode != 0:
                    return ToolResult(error=f"Tool failed: {result.stderr.strip()}")

                # Try to parse JSON output, fall back to raw text
                stdout = result.stdout.strip()
                try:
                    data = json.loads(stdout)
                except json.JSONDecodeError:
                    data = {"output": stdout}

                return ToolResult(data=data)
            finally:
                script_path.unlink(missing_ok=True)

        except subprocess.TimeoutExpired:
            return ToolResult(error=f"Tool timed out after {_TOOL_TIMEOUT}s")
        except Exception as e:
            logger.error("domain_tool_error", tool=tool.name, error=str(e))
            return ToolResult(error=str(e))

    return ToolDef(
        name=f"domain_{tool.name}",
        description=tool.description or f"Domain tool: {tool.name}",
        parameters=tool.parameters or {"type": "object", "properties": {}},
        handler=handler,
    )


def _build_script(code: str, args: dict[str, Any]) -> str:
    """Build an executable script from tool code and arguments.

    The code is expected to either:
    1. Define a `main(args)` function — we call it with the args dict
    2. Be a standalone script — we inject `args` as a global variable
    """
    args_json = json.dumps(args, default=str)
    return f"""import json
import sys

# Injected arguments
args = json.loads('''{args_json}''')

# Domain tool code
{code}

# If the code defines a main() function, call it
if 'main' in dir():
    result = main(args)
    if result is not None:
        print(json.dumps(result, default=str))
"""
