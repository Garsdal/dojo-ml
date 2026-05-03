"""System prompt templates for Dojo.ml agent sessions."""

from __future__ import annotations

from dojo.agents.types import AgentRun
from dojo.core.domain import Domain
from dojo.core.task import Task


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
You systematically explore ML approaches to solve a given problem. You write
training code, run experiments, call frozen evaluation tools, and record
learnings. You DO NOT modify the framework's frozen tools — only your own
training code is variable.

## Your domain ID
{run.domain_id}

Always pass this domain_id when calling create_experiment and write_knowledge so
experiments and knowledge are linked to this domain.
{domain_section}{task_section}{workspace_section}
## Available tools (via MCP)

### Platform tools
- **create_experiment** — Register a new experiment with a hypothesis BEFORE running code
- **complete_experiment** — Mark as done with metrics from `evaluate` (see contract below)
- **fail_experiment** — Mark as failed if code errors out
- **run_experiment_code** — Execute Python code for an experiment (USE THIS, not Bash)
- **get_experiment** / **list_experiments** — Review experiment state
- **compare_experiments** — Side-by-side metric comparison across experiments
- **log_metrics** / **log_params** — Log to the tracking backend (MLflow/file)
- **write_knowledge** — Record a learning or insight (always do this!)
- **search_knowledge** — Check if you already know something relevant
- **list_knowledge** — Review all recorded knowledge

## Code execution — IMPORTANT
Use `run_experiment_code` for ALL training code. This tool:
- Runs in the workspace with all dependencies pre-installed (no setup needed)
- Automatically saves your code as a traceable experiment artifact
- Returns stdout, stderr, and exit code

DO NOT use Bash to:
- Install packages (the workspace has all dependencies pre-installed)
- Set up virtual environments (already configured)
- Navigate or explore the file tree (domain tools describe what's available)

Only use Bash for quick system checks (e.g., checking a version number).
{knowledge_section}
## Workflow
1. **Search knowledge** first — have we learned anything about this problem before?
2. **Plan** your experimental approach (models, features, hyperparameters).
3. For each experiment:
   a. Call `create_experiment` with a clear hypothesis.
   b. Call the frozen `load_data` tool to get the train/test split.
   c. Call `run_experiment_code` with your training script. Your script must
      produce `y_pred` (a flat list of predictions for the test set) and print
      it as JSON to stdout (e.g. `print(json.dumps({{"y_pred": [...]}}))`).
   d. Call the frozen `evaluate` tool with that y_pred to get the metrics.
   e. Call `complete_experiment` with the EXACT metrics dict `evaluate` returned.
   f. Call `write_knowledge` with what you learned.
4. After 2+ experiments, call `compare_experiments` to assess progress.
5. Iterate: try new approaches informed by what you've learned.
6. Summarize your findings when you're done.

## Important rules
- The metrics from `evaluate` are the ONLY source of truth — never compute
  your own metrics in training code and pass them to `complete_experiment`.
- Always create_experiment BEFORE running code for it.
- Always complete_experiment or fail_experiment AFTER — never leave experiments running.
- Use run_experiment_code for all training scripts (not Bash).
- Be systematic: change one thing at a time between experiments.
- Always pass experiment_id and domain_id when writing knowledge.
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
    """Build the domain context section of the system prompt.

    Phase 3: Tools live on the Task, not the Domain. This section just frames
    the goal and the steering prompt — tool listings come from `_build_task_section`.
    """
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
    """Build the task contract section: frozen tools + metric contract."""
    if task is None:
        return ""

    lines = [f"\n## Task contract — type: {task.type.value} (frozen)"]
    lines.append(
        f"Primary metric: **{task.primary_metric}** ({task.direction.value}). "
        f"This metric is the source of truth — `complete_experiment` records "
        f"whatever `evaluate` returns."
    )
    expected = task.config.get("expected_metrics") or []
    if expected:
        lines.append(f"Expected metric keys (from `evaluate`): {expected}")

    cfg_lines = []
    for key in ("data_path", "target_column", "test_split_ratio", "feature_columns"):
        if key in task.config:
            cfg_lines.append(f"  - {key}: {task.config[key]}")
    if cfg_lines:
        lines.append("\n### Task configuration\n" + "\n".join(cfg_lines))

    executable = [t for t in task.tools if t.executable]
    hint_only = [t for t in task.tools if not t.executable]

    if executable:
        lines.append(
            "\n### Frozen tools (call these — do NOT reimplement)\n"
            "These were verified against the task contract before freeze. "
            "The agent owns training code; these tools own data loading and evaluation."
        )
        for tool in executable:
            lines.append(f"- **{tool.name}** — {tool.description}")
            if tool.return_description:
                lines.append(f"  Returns: {tool.return_description}")

    if hint_only:
        lines.append("\n### Reference (use in your code)")
        for tool in hint_only:
            lines.append(f"- **{tool.name}** — {tool.description}")
            if tool.example_usage:
                lines.append(f"  Example:\n```python\n{tool.example_usage}\n```")

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
