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
    """Specifies the function-shaped interface a generated tool must conform to.

    Phase 4: tools are Python modules with a named entrypoint. The verifier
    imports the module, calls ``entrypoint(**fixtures)``, and checks the
    return value against ``returns_schema`` interpreted via ``return_kind``.

    `return_kind`:
      - "dict" (default): return value is a dict — schema keys are dict keys.
      - "tuple": return value is a tuple/list — schema keys are positional
        items, in order. Length must match ``len(returns_schema)``.
    """

    name: str
    description: str
    entrypoint: str = ""
    module_filename: str = ""
    params_schema: dict[str, str] = field(default_factory=dict)
    returns_schema: dict[str, str] = field(default_factory=dict)
    return_kind: str = "dict"


@dataclass
class TaskTypeSpec:
    """Registry entry for a task type — shared across all domains of that type."""

    default_metric: str
    default_direction: Direction
    required_tools: list[ToolContract]
    generation_prompt_template: str
    config_schema: dict[str, Any]  # which Task.config fields are required/optional
    train_output_description: str = ""  # what `def train()` must return


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
You are generating Python tool **modules** for a regression ML task.

Domain: {domain_name}
{domain_description}

{program_md_section}
## Structured hints (optional — PROGRAM.md wins if they conflict)
  data_path: {data_path}
  target_column: {target_column}
  test_split_ratio: {test_split_ratio}
  feature_columns: {feature_columns}

{hint_section}

## How to read this
- The PROGRAM.md block above is the user's spec — it tells you where the data
  lives and what the target is, in plain English. Trust it.
- The PROGRAM.md may contain a `## Dataset` section (steers `load_data`) and an
  `## Evaluate` section (steers what's *inside* `evaluate`, but never its
  signature). Read both before writing each module.
- For sklearn-bundled datasets (e.g. fetch_california_housing, load_diabetes),
  the user typically points you at the loader function — there is NO csv path
  and NO column name. Use the loader directly:
    from sklearn.datasets import fetch_california_housing
    X, y = fetch_california_housing(return_X_y=True)
- For local CSVs, use the data_path / target_column hints if PROGRAM.md
  doesn't give you better info.
- For URLs, download via pandas/requests (the workspace has internet).
- If the user's `## Dataset` describes an expensive fetch, **cache the result
  to disk** (e.g. `Path("cache") / dataset_name / "X.parquet"`) inside
  `load_data` so subsequent calls are fast. The verifier reuses the same
  module directory across runs, so the cache persists.

## Output: exactly two Python modules

The framework imports these modules and calls the named functions. The agent's
`def train()` (written separately at run-time) runs in the same Python process
as `evaluate`, so `y_pred` never leaves memory.

Module 1 — load_data.py
- Defines a top-level function: `def load_data():`
- Takes no parameters.
- Loads the dataset, splits into train/test using test_split_ratio.
- Use a deterministic split (random_state=42) so evaluate sees the same y_test.
- Returns a 4-tuple: (X_train, X_test, y_train, y_test). Each element is a
  list-of-lists or list (numpy arrays are fine — the framework converts).
- Must NOT print to stdout — return only.

Module 2 — evaluate.py
- Defines a top-level function: `def evaluate(y_pred):`
  where `y_pred` is {train_output_description}.
- May import from load_data: `from load_data import load_data`.
- Reproduces the same split as load_data (call `load_data()` and unpack the
  4-tuple) to get y_test.
- Computes: rmse (float), r2 (float), mae (float).
- Returns a dict with exactly those three keys: {{"rmse": ..., "r2": ..., "mae": ...}}.
- Must NOT print to stdout — return only.

Output format (respond with ONLY this JSON, no markdown):
[
  {{
    "name": "load_data",
    "filename": "load_data.py",
    "entrypoint": "load_data",
    "description": "Load and split the dataset described in PROGRAM.md",
    "type": "data_loader",
    "code": "<python module source as a string>"
  }},
  {{
    "name": "evaluate",
    "filename": "evaluate.py",
    "entrypoint": "evaluate",
    "description": "Evaluate regression predictions — returns rmse, r2, mae",
    "type": "evaluator",
    "code": "<python module source as a string>"
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
                description="Load the dataset and return a (X_train, X_test, y_train, y_test) tuple",
                entrypoint="load_data",
                module_filename="load_data.py",
                params_schema={},
                returns_schema={
                    "X_train": "list of lists (float)",
                    "X_test": "list of lists (float)",
                    "y_train": "list of float",
                    "y_test": "list of float",
                },
                return_kind="tuple",
            ),
            ToolContract(
                name="evaluate",
                description="Evaluate model predictions; receives y_pred as the only argument",
                entrypoint="evaluate",
                module_filename="evaluate.py",
                params_schema={"y_pred": "list of float"},
                returns_schema={
                    "rmse": "float",
                    "r2": "float",
                    "mae": "float",
                },
                return_kind="dict",
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
        train_output_description="a flat list of float predictions for the test set, in the same order as X_test from load_data()",
    ),
}
