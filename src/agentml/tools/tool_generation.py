"""AI-assisted tool generation for research domains.

Uses a structured prompt to generate DomainTool definitions
(name, description, type, example_usage, parameters) from a domain description.
"""

from __future__ import annotations

import json
import re
from typing import Any

from agentml.core.domain import Domain, DomainTool, ToolType
from agentml.utils.logging import get_logger

logger = get_logger(__name__)

# Valid tool types
_VALID_TYPES = {t.value for t in ToolType}


def build_tool_generation_prompt(domain: Domain, hint: str = "") -> str:
    """Build a prompt for generating domain-specific tools.

    Args:
        domain: The domain to generate tools for.
        hint: Optional user hint about what kind of tools to generate.

    Returns:
        A prompt string suitable for passing to an agent/LLM.
    """
    existing_tools = ""
    if domain.tools:
        names = ", ".join(t.name for t in domain.tools)
        existing_tools = f"\nExisting tools: {names}\nDo NOT duplicate these."

    return f"""You are a tool-generation assistant for an ML research platform.

## Domain
- Name: {domain.name}
- Description: {domain.description}
- Prompt: {domain.prompt}
{existing_tools}

## Task
Generate semantic tool descriptors for this domain. Each tool describes a
capability the agent should have — the agent writes its own code to use them.
{f"User hint: {hint}" if hint else ""}

## Output Format
Return a JSON array of tool objects. Each tool must have:
- "name": snake_case name (e.g. "load_dataset", "evaluate_model")
- "description": What the tool does (1-2 sentences)
- "type": One of {sorted(_VALID_TYPES)}
- "parameters": JSON object describing input parameters (JSON Schema style)
- "example_usage": A short Python snippet showing how the agent might use this tool

## Example
```json
[
  {{
    "name": "load_csv_dataset",
    "description": "Load a CSV file and return basic statistics",
    "type": "data_loader",
    "parameters": {{
      "file_path": {{"type": "string", "description": "Path to CSV file"}}
    }},
    "example_usage": "import pandas as pd\\ndf = pd.read_csv('data.csv')\\nprint(df.describe())"
  }}
]
```

Generate 2-4 tools that would be most useful for this domain. Return ONLY the JSON array."""


def parse_generated_tools(raw_output: str) -> list[dict[str, Any]]:
    """Parse LLM output into tool definition dicts.

    Extracts JSON from the output, handling markdown code fences.

    Returns:
        List of validated tool definition dicts.

    Raises:
        ValueError: If the output cannot be parsed or validated.
    """
    # Try to extract JSON array from the output
    # Handle ```json ... ``` wrapping
    json_match = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", raw_output, re.DOTALL)
    if json_match:
        raw_json = json_match.group(1)
    else:
        # Try to find a bare JSON array
        array_match = re.search(r"\[.*\]", raw_output, re.DOTALL)
        if array_match:
            raw_json = array_match.group(0)
        else:
            raise ValueError("No JSON array found in output")

    try:
        tools = json.loads(raw_json)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON: {e}") from e

    if not isinstance(tools, list):
        raise ValueError("Expected a JSON array of tools")

    validated = []
    for i, tool in enumerate(tools):
        validated.append(_validate_tool_dict(tool, index=i))

    return validated


def _validate_tool_dict(tool: dict[str, Any], *, index: int = 0) -> dict[str, Any]:
    """Validate a single tool definition dict.

    Raises ValueError if required fields are missing or invalid.
    """
    if not isinstance(tool, dict):
        raise ValueError(f"Tool {index}: expected dict, got {type(tool).__name__}")

    # Required fields
    name = tool.get("name")
    if not name or not isinstance(name, str):
        raise ValueError(f"Tool {index}: 'name' is required and must be a string")

    # Sanitize name to snake_case
    name = re.sub(r"[^a-z0-9_]", "_", name.lower().strip())
    if not name:
        raise ValueError(f"Tool {index}: name is empty after sanitization")

    description = tool.get("description", "")
    tool_type = tool.get("type", "custom")
    if tool_type not in _VALID_TYPES:
        tool_type = "custom"

    example_usage = tool.get("example_usage", "")
    if not isinstance(example_usage, str):
        raise ValueError(f"Tool {index}: 'example_usage' must be a string")

    parameters = tool.get("parameters", {})
    if not isinstance(parameters, dict):
        parameters = {}

    return {
        "name": name,
        "description": str(description),
        "type": tool_type,
        "example_usage": example_usage,
        "parameters": parameters,
    }


def dicts_to_domain_tools(
    tool_dicts: list[dict[str, Any]],
    *,
    created_by: str = "ai",
) -> list[DomainTool]:
    """Convert validated tool dicts into DomainTool instances."""
    return [
        DomainTool(
            name=d["name"],
            description=d["description"],
            type=ToolType(d["type"]),
            example_usage=d["example_usage"],
            parameters=d["parameters"],
            created_by=created_by,
        )
        for d in tool_dicts
    ]
