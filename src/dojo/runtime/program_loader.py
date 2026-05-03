"""PROGRAM.md loader — Karpathy-style human-editable steering prompt.

A `PROGRAM.md` file lives under the domain's local state and acts as the
agent's steering prompt. Editing the file between runs is the lightest
possible feedback loop — no API call, no UI.

Resolution order for a domain's program path:
1. `domain.program_path` if set (explicit override)
2. `<base_dir>/domains/{id}/PROGRAM.md` (default — keeps the user's repo clean)

At agent run start, the orchestrator reads the file (if present) and uses its
content as the steering prompt. Falls back to `domain.prompt` if the file is
missing or empty — preserves existing behaviour for callers that haven't
adopted PROGRAM.md yet.
"""

from __future__ import annotations

from pathlib import Path

from dojo.core.domain import Domain


def resolve_program_path(domain: Domain, *, base_dir: Path | None = None) -> Path:
    """Return the canonical PROGRAM.md path for a domain.

    Does not check existence — callers decide what to do when the file is missing.
    """
    if domain.program_path:
        return Path(domain.program_path).expanduser()
    base = Path(base_dir) if base_dir is not None else Path(".dojo")
    return base / "domains" / domain.id / "PROGRAM.md"


def load_program(domain: Domain, *, base_dir: Path | None = None) -> str:
    """Read the domain's PROGRAM.md, falling back to `domain.prompt`.

    Returns an empty string if neither source has content.
    """
    path = resolve_program_path(domain, base_dir=base_dir)
    if path.exists():
        content = path.read_text().strip()
        if content:
            return content
    return domain.prompt or ""


def write_program(domain: Domain, content: str, *, base_dir: Path | None = None) -> Path:
    """Write content to the domain's PROGRAM.md path. Creates parent dirs.

    Returns the path that was written.
    """
    path = resolve_program_path(domain, base_dir=base_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return path


_DEFAULT_TEMPLATE = """\
# {name}

> Steering prompt for the Dojo.ml agent and the source of truth for tool
> generation. Edit freely between runs — `dojo task setup` reads this file to
> generate `load_data` and `evaluate`, and the agent reads it at the start of
> each run.

## Goal
{description}

## Task type
{task_type}

## Dataset
<!--
Describes where the data lives and how to load it. The AI uses this to write
`load_data`. A few examples:

- sklearn loader:
    Use `sklearn.datasets.fetch_california_housing(return_X_y=True)`.
    Features and target both come back as numpy arrays — no column names.
    https://scikit-learn.org/stable/modules/generated/sklearn.datasets.fetch_california_housing.html

- Local CSV:
    `./data/housing.csv` — features are every column except `MedHouseVal`,
    target is `MedHouseVal`.

- URL:
    Download `https://example.com/data.csv` on first call (cache to `./data/`).
-->
TODO — describe the dataset here.

## Evaluate
<!--
Describes what `evaluate(y_pred)` should compute. The AI uses this to write
`evaluate`. The signature is fixed by the contract below — `def evaluate(y_pred)`
returning `{{"rmse", "r2", "mae"}}` — but you can steer what's *inside* it.

A few examples:

- "Use sklearn's mean_squared_error / r2_score / mean_absolute_error against
  the y_test produced by load_data()."
- "Wrap our existing evaluator: `from mypkg.evaluation import evaluate as
  _impl; metrics = _impl(y_test, y_pred)` and return its dict."
- "Weight errors by sample_weight from load_data()'s test split."

Leave blank for the default (sklearn-style metrics on the full y_test).
-->
TODO — describe how evaluation should work, or leave blank for the default.

## Target
<!--
What is the model predicting? A single sentence is enough.
For sklearn-style (X, y) datasets, just describe the target — there is no
column name.
-->
TODO — describe the target.

## Success
<!--
How do you know the agent did well? RMSE under some threshold, beating a
linear baseline, etc. The agent reads this and uses it to plan experiments.
-->
TODO — describe what success looks like.

## Contract (do not edit — generated tools are pinned to this)
- The agent owns `train()` and any model / hyperparameter logic, called via
  `run_experiment_code`.
- `load_data` and `evaluate` are frozen tools the agent calls but cannot
  modify. The dict returned by `evaluate` is the only metric source of truth.

## Notes
- Bullet hypotheses you've ruled out, things you've tried, references to past
  runs. The agent reads this section every run.
"""


def default_program_template(domain: Domain) -> str:
    """Return a default PROGRAM.md template for a fresh domain."""
    task_type = domain.task.type.value if domain.task else "(not set)"
    return _DEFAULT_TEMPLATE.format(
        name=domain.name or "Untitled domain",
        description=domain.description or "(describe the research goal)",
        task_type=task_type,
    )
