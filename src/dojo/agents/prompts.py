"""System prompt templates for Dojo.ml agent sessions (Phase 4 — function contract)."""

from __future__ import annotations

from dojo.agents.types import AgentRun
from dojo.core.domain import Domain
from dojo.core.task import TASK_TYPE_REGISTRY, Task


def build_system_prompt(
    run: AgentRun,
    *,
    domain: Domain | None = None,
    accumulated_knowledge: list[str] | None = None,
) -> str:
    """Build the system prompt for an agent session."""
    hints_section = _build_hints_section(run)
    domain_section = _build_domain_section(domain)
    task_section = _build_task_section(domain.task if domain else None)
    workspace_section = _build_workspace_section(domain)
    knowledge_section = _build_knowledge_section(accumulated_knowledge)

    return f"""You are an autonomous ML research agent operating within Dojo.ml.

## Your role
You systematically explore ML approaches to solve a given problem. Each
experiment is a single ``run_experiment`` MCP call: you submit Python source
defining ``def train()``, the framework runs it against frozen ``load_data``
and ``evaluate``, and returns the metrics. You DO NOT modify the framework's
frozen tools — only your own ``train()`` is variable.

## Your domain ID
{run.domain_id}

Always pass this domain_id when calling ``run_experiment`` and ``write_knowledge``
so experiments and knowledge are linked to this domain.
{domain_section}{task_section}{workspace_section}
## Available tools (via MCP)

### Per-experiment driver
- **run_experiment** — Submit ``train_code`` (Python module string) along with
  a hypothesis. The framework creates the experiment, runs your ``def train()``
  against the frozen ``load_data`` + ``evaluate``, parses metrics, and records
  the result. Returns ``{{experiment_id, status, metrics, stdout, stderr,
  exit_code, run_number}}``.

### Read-only observability
- **get_experiment** / **list_experiments** — Inspect prior experiments.
- **compare_experiments** — Side-by-side metric comparison across IDs.

### Knowledge
- **search_knowledge** — Check what we already know about this problem.
- **list_knowledge** — Browse all recorded knowledge for the domain.
- **write_knowledge** — Record a learning, tied to an experiment_id.

### Optional intermediate logging
- **log_metrics** / **log_params** — Use only if you want to log per-epoch /
  per-step values during training. The experiment-final metric is recorded
  automatically by ``run_experiment`` from ``evaluate``'s return value.
{knowledge_section}
## Workflow
1. ``search_knowledge`` — what do we already know? Prefer this over
   ``list_experiments`` for orientation: the accumulated_knowledge section
   above already summarises prior runs, so you usually don't need to enumerate
   raw experiments at all.
2. Plan one hypothesis worth testing.
3. ``run_experiment(domain_id, hypothesis, train_code)`` — your ``train_code``
   defines ``def train()`` returning the task-specific output (regression: a
   flat list of float predictions for the test set).
4. If — and only if — the result is non-obvious or worth carrying forward
   (e.g. a model class beats another by a meaningful margin, a hyperparameter
   range is dead, a feature trick helps/hurts), call ``write_knowledge`` with
   a tight one-sentence claim and the experiment_id. Skip it for routine
   incremental tuning.
5. After 2+ experiments, ``compare_experiments`` to assess progress.
6. Iterate. Change one thing at a time between experiments.

## Example train_code

```python
from load_data import load_data
from sklearn.linear_model import LinearRegression


def train():
    X_train, X_test, y_train, _ = load_data()
    model = LinearRegression().fit(X_train, y_train)
    return model.predict(X_test).tolist()
```

The agent owns ``train()`` only. ``load_data`` is frozen and shared across
experiments — that's why metrics are comparable.

## Important rules
- Metrics come from the framework, not from you. Never compute or pass metrics
  yourself; the dict returned by ``evaluate`` is the only source of truth.
- A failed ``run_experiment`` (broken train code) is fine — fix and call
  ``run_experiment`` again with the same hypothesis if the idea is still
  worth testing. Each call is its own experiment record.
- Be systematic: change one thing at a time between experiments.
- Be selective with ``write_knowledge`` — record only durable findings worth
  carrying into future runs. Don't bloat the store with per-experiment recaps.
{hints_section}"""


def _build_hints_section(run: AgentRun) -> str:
    """Build the tool hints section of the system prompt."""
    if not run.tool_hints:
        return ""

    lines = ["\n## Data sources & hints"]
    lines.append("The user has provided the following information:\n")
    for hint in run.tool_hints:
        lines.append(f"- **{hint.name}**: {hint.description}")
        lines.append(f"  Source: {hint.source}")
        if hint.code_template:
            lines.append(f"  Starter code:\n```python\n{hint.code_template}\n```")
    lines.append("\nFetch these sources if needed, then write appropriate data loading code.")
    return "\n".join(lines)


def _build_workspace_section(domain: Domain | None) -> str:
    """Build the workspace context section."""
    if domain is None or domain.workspace is None or not domain.workspace.ready:
        return ""

    ws = domain.workspace
    lines = ["\n## Workspace environment"]
    lines.append(f"Your working directory is: `{ws.path}`")
    lines.append(
        "All dependencies are pre-installed — DO NOT install packages or set up environments."
    )
    if ws.python_path:
        lines.append(f"Python executable: `{ws.python_path}`")
    return "\n".join(lines)


def _build_domain_section(domain: Domain | None) -> str:
    """Build the domain context section: name, description, steering prompt."""
    if domain is None:
        return ""

    lines = [f"\n## Domain: {domain.name}"]
    if domain.description:
        lines.append(domain.description)
    if domain.prompt:
        lines.append(f"\n### Steering prompt (PROGRAM.md)\n{domain.prompt}")

    if domain.config:
        lines.append(f"\n### Domain configuration\n{domain.config}")

    return "\n".join(lines)


def _build_task_section(task: Task | None) -> str:
    """Frame the function-based contract: agent owns train(), framework owns the rest."""
    if task is None:
        return ""

    spec = TASK_TYPE_REGISTRY.get(task.type)
    train_output = spec.train_output_description if spec and spec.train_output_description else ""

    lines = [f"\n## Task contract — type: {task.type.value} (frozen)"]
    lines.append(
        f"Primary metric: **{task.primary_metric}** ({task.direction.value}). "
        f"This metric is the source of truth — ``run_experiment`` records "
        f"whatever ``evaluate`` returns."
    )
    expected = task.config.get("expected_metrics") or []
    if expected:
        lines.append(f"Expected metric keys (from `evaluate`): {expected}")

    lines.append(
        "\n### Contract\n"
        "- **You own**: ``def train()`` — the only thing variable across experiments.\n"
        "- **The framework owns**: ``load_data()`` and ``evaluate(y_pred)`` — "
        "loaded from a canonical, frozen path. Don't try to override them.\n"
        f"- **``train()`` must return**: {train_output or 'the task-specific output'}.\n"
        "- The framework runs ``train()`` and ``evaluate(train())`` in the "
        "same Python process; metrics are recorded automatically."
    )

    cfg_lines = []
    for key in ("data_path", "target_column", "test_split_ratio", "feature_columns"):
        if key in task.config:
            cfg_lines.append(f"  - {key}: {task.config[key]}")
    if cfg_lines:
        lines.append("\n### Task configuration\n" + "\n".join(cfg_lines))

    return "\n".join(lines)


def _build_knowledge_section(accumulated_knowledge: list[str] | None) -> str:
    """Build accumulated knowledge section for domain-aware runs."""
    if not accumulated_knowledge:
        return ""

    lines = ["\n## Accumulated knowledge from this domain"]
    lines.append("Previous experiments in this domain have established:\n")
    lines.extend(accumulated_knowledge)
    lines.append("\nBuild on this knowledge — don't repeat experiments already covered.")
    return "\n".join(lines)
