"""Task abstraction — the anti-cheating contract for a research domain.

A Task defines what is frozen (data loading + evaluation) and what the agent
is allowed to change (training code). Every experiment in a domain runs against
the same frozen Task contract, making metrics comparable and trustworthy.

Only RegressionTask (TaskType.REGRESSION) is supported for now. Other types
will be added to TASK_TYPE_REGISTRY when regression is solid end-to-end.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, ClassVar

from dojo.utils.ids import generate_id


class TaskType(StrEnum):
    REGRESSION = "regression"


class Direction(StrEnum):
    MINIMIZE = "minimize"
    MAXIMIZE = "maximize"


@dataclass
class ToolContract:
    """Specifies the interface a generated tool must conform to.

    The ToolVerifier (Phase 3) checks that the actual tool output matches
    returns_schema before the task can be frozen.
    """

    name: str
    description: str
    params_schema: dict[str, str] = field(default_factory=dict)
    returns_schema: dict[str, str] = field(default_factory=dict)


@dataclass
class TaskTypeSpec:
    """Registry entry for a task type — shared across all domains of that type."""

    default_metric: str
    default_direction: Direction
    required_tools: list[ToolContract]
    generation_prompt_template: str
    config_schema: dict[str, Any]  # which Task.config fields are required/optional


@dataclass
class Task:
    """The contract for a domain's research loop.

    frozen=False: tools can be regenerated and edited; agent runs are blocked.
    frozen=True:  tools are immutable for all subsequent runs; agent runs allowed.
    """

    id: str = field(default_factory=generate_id)
    type: TaskType = TaskType.REGRESSION
    name: str = ""
    description: str = ""
    primary_metric: str = "rmse"
    direction: Direction = Direction.MINIMIZE
    tools: list[Any] = field(default_factory=list)  # list[DomainTool] — avoids circular import
    config: dict[str, Any] = field(default_factory=dict)
    frozen: bool = False
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_REGRESSION_PROMPT = """\
You are generating Python tool code for a regression ML task.

Domain: {domain_name}
{domain_description}

Task configuration:
  data_path: {data_path}
  target_column: {target_column}
  test_split_ratio: {test_split_ratio}
  feature_columns: {feature_columns}

{hint_section}

Generate exactly two tools as a JSON array.

Tool 1 — load_data
- No parameters
- Loads the dataset from data_path, splits into train/test using test_split_ratio
- Returns JSON with keys: X_train (list), X_test (list), y_train (list), y_test (list)
- Each value is a list of lists (for X) or a flat list (for y)
- Prints the JSON to stdout; no return statement needed
- Do NOT print anything else to stdout

Tool 2 — evaluate
- Receives y_pred injected as a local variable (a flat list of floats)
- Loads y_test from the same split as load_data (use the same random_state)
- Computes: rmse (float), r2 (float), mae (float)
- Returns JSON with exactly those three keys
- Prints the JSON to stdout; do NOT print anything else

Output format (respond with ONLY this JSON, no markdown):
[
  {{
    "name": "load_data",
    "description": "Load and split {target_column} dataset",
    "type": "data_loader",
    "example_usage": "# Call load_data() to get X_train, X_test, y_train, y_test",
    "parameters": {{}},
    "code": "<python code as a string>"
  }},
  {{
    "name": "evaluate",
    "description": "Evaluate regression predictions — returns rmse, r2, mae",
    "type": "evaluator",
    "example_usage": "# Called with y_pred injected; returns {{rmse, r2, mae}}",
    "parameters": {{"y_pred": {{"type": "array", "items": {{"type": "number"}}}}}},
    "code": "<python code as a string>"
  }}
]
"""

TASK_TYPE_REGISTRY: ClassVar[dict[TaskType, TaskTypeSpec]] = {
    TaskType.REGRESSION: TaskTypeSpec(
        default_metric="rmse",
        default_direction=Direction.MINIMIZE,
        required_tools=[
            ToolContract(
                name="load_data",
                description="Load the dataset and return a train/test split",
                params_schema={},
                returns_schema={
                    "X_train": "list of lists (float)",
                    "X_test": "list of lists (float)",
                    "y_train": "list of float",
                    "y_test": "list of float",
                },
            ),
            ToolContract(
                name="evaluate",
                description="Evaluate model predictions; y_pred injected as local variable",
                params_schema={"y_pred": "list of float"},
                returns_schema={
                    "rmse": "float",
                    "r2": "float",
                    "mae": "float",
                },
            ),
        ],
        generation_prompt_template=_REGRESSION_PROMPT,
        config_schema={
            "required": ["data_path", "target_column"],
            "optional": {
                "test_split_ratio": 0.2,
                "feature_columns": [],
                "random_state": 42,
            },
        },
    ),
}
