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
    runner_callsite: str
    verifier_fixture_keys: dict[str, dict[str, str]]
    contract_version: int
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
- It contains two paired sections that map 1:1 onto the modules you're writing:
    - `## Dataset` ⟶ steers `load_data.py`. Read this before writing module 1.
    - `## Evaluate` ⟶ steers what goes *inside* `evaluate.py`. Read this before
      writing module 2. (The signature is
      `def evaluate(y_pred, *, X_train, X_test, y_train, y_test)` returning
      `{{"rmse", "r2", "mae"}}` — only the body is yours to shape.)
  If `## Evaluate` is empty/TODO, default to sklearn-style metrics on y_test.
  If it points at an existing project evaluator, wrap it.
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

## Artifacts
- The framework provides a per-run directory via the env var
  ``DOJO_ARTIFACTS_DIR``. Use it for any files you produce — plots, model
  checkpoints, intermediate CSVs.
- Read it as ``Path(os.environ["DOJO_ARTIFACTS_DIR"])``.
- Do **not** write to a relative ``artifacts/`` directory or anywhere else
  in the workspace — those paths are shared across experiments and the
  framework will not capture them. Files written under
  ``DOJO_ARTIFACTS_DIR`` are auto-registered into the artifact store and
  forwarded to the tracking backend.

## Output: exactly two Python modules

The framework imports these modules and calls the named functions. The agent's
`def train()` (written separately at run-time) runs in the same Python process
as `evaluate`, so `y_pred` never leaves memory.

Module 1 — load_data.py
- Defines a top-level function: `def load_data():`
- Takes no parameters.
- Loads the dataset, splits into train/test using test_split_ratio.
- Use a deterministic split (random_state=42) so evaluate sees the same y_test.
- Returns a 4-tuple: (X_train, X_test, y_train, y_test). Each element can be
  a list, numpy array, pandas DataFrame/Series, or polars frame — the
  framework converts to JSON-safe shapes via `.tolist()` / `.to_numpy()`.
- Must NOT print to stdout — return only.

Module 2 — evaluate.py
- Defines a top-level function:
  `def evaluate(y_pred, *, X_train, X_test, y_train, y_test) -> dict`.
- Receives all data as parameters — do **not** call ``load_data`` inside
  ``evaluate``. The framework loads data once and passes the splits in.
- Computes: rmse (float), r2 (float), mae (float) against ``y_test``.
- Returns a dict with exactly those three keys: {{"rmse": ..., "r2": ..., "mae": ...}}.
- Must NOT print to stdout — return only.
- May write debugging / summary files into ``DOJO_ARTIFACTS_DIR`` (see
  the Artifacts section above).

## Train (agent's per-experiment code, written separately)
The framework expects the agent's training code to define:
  ``def train(X_train, y_train, X_test) -> y_pred``
where ``y_pred`` is {train_output_description}. The framework calls
``train`` with the splits from ``load_data()`` — do not call
``load_data`` from inside ``train`` either.

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
                description=(
                    "Evaluate model predictions; receives y_pred plus the "
                    "train/test splits so the agent code does not need to "
                    "call load_data internally."
                ),
                entrypoint="evaluate",
                module_filename="evaluate.py",
                params_schema={
                    "y_pred": "list of float",
                    "X_train": "list of lists (float)",
                    "X_test": "list of lists (float)",
                    "y_train": "list of float",
                    "y_test": "list of float",
                },
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
        runner_callsite=(
            "y_pred = train(X_train, y_train, X_test)\n"
            "    metrics = evaluate("
            "y_pred, "
            "X_train=X_train, "
            "X_test=X_test, "
            "y_train=y_train, "
            "y_test=y_test)"
        ),
        verifier_fixture_keys={
            "evaluate": {
                "y_pred": "y_test",
                "X_train": "X_train",
                "X_test": "X_test",
                "y_train": "y_train",
                "y_test": "y_test",
            },
        },
        contract_version=2,
        train_output_description="a flat list of float predictions for the test set, in the same order as X_test from load_data()",
    ),
}
