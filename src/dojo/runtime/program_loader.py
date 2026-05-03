"""PROGRAM.md loader — Karpathy-style human-editable steering prompt.

A `PROGRAM.md` file lives next to the workspace (or under the domain's local
state) and acts as the agent's steering prompt. Editing the file between runs
is the lightest possible feedback loop — no API call, no UI.

Resolution order for a domain's program path:
1. `domain.program_path` if set (explicit override)
2. `<workspace.path>/PROGRAM.md` if a workspace path is set
3. `<base_dir>/domains/{id}/PROGRAM.md` (domain-local fallback)

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
    if domain.workspace and domain.workspace.path:
        return Path(domain.workspace.path) / "PROGRAM.md"
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

> Steering prompt for the Dojo.ml agent. Edit freely between runs — the agent
> reads this file at the start of each run.

## Goal
{description}

## Task type
{task_type}

## What the agent owns
- Writing the `train()` function and any model selection / hyperparameter logic
- Running experiments via `run_experiment_code`
- Recording knowledge atoms with `write_knowledge`

## What the framework owns (frozen, do not modify)
- `load_data` — produces the same train/test split every run
- `evaluate` — computes the metrics that decide success

## Notes
- Replace this section with anything you want the agent to focus on.
- Bullet hypotheses you've ruled out, references to past runs, etc.
"""


def default_program_template(domain: Domain) -> str:
    """Return a default PROGRAM.md template for a fresh domain."""
    task_type = domain.task.type.value if domain.task else "(not set)"
    return _DEFAULT_TEMPLATE.format(
        name=domain.name or "Untitled domain",
        description=domain.description or "(describe the research goal)",
        task_type=task_type,
    )
