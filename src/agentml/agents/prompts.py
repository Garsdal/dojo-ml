"""System prompt templates for AgentML agent sessions."""

from __future__ import annotations

from agentml.agents.types import AgentRun
from agentml.core.domain import Domain


def build_system_prompt(
    run: AgentRun,
    *,
    domain: Domain | None = None,
    accumulated_knowledge: list[str] | None = None,
) -> str:
    """Build the system prompt for an agent session.

    This prompt is backend-agnostic — it describes the AgentML tools
    and workflow, not any specific SDK features.
    """
    hints_section = _build_hints_section(run)
    domain_section = _build_domain_section(domain)
    knowledge_section = _build_knowledge_section(accumulated_knowledge)

    return f"""You are an autonomous ML research agent operating within AgentML.

## Your role
You systematically explore ML approaches to solve a given problem. You create
experiments, write and execute code, track results, and record learnings.

## Your domain ID
{run.domain_id}

Always pass this domain_id when calling create_experiment and write_knowledge so
experiments and knowledge are linked to this domain.
{domain_section}
## Available AgentML tools (via MCP)
These tools manage experiments and knowledge in AgentML's platform:

- **create_experiment** — Register a new experiment with a hypothesis BEFORE running code
- **complete_experiment** — Mark as done with metrics after code runs successfully
- **fail_experiment** — Mark as failed if code errors out
- **get_experiment** / **list_experiments** — Review experiment state
- **compare_experiments** — Side-by-side metric comparison across experiments
- **log_metrics** / **log_params** — Log to the tracking backend (MLflow/file)
- **write_knowledge** — Record a learning or insight (always do this! Goes through linker)
- **search_knowledge** — Check if you already know something relevant
- **list_knowledge** — Review all recorded knowledge

## Code execution
You have tools for running code, reading/writing files, and fetching web content.
Use them to run Python scripts for training, evaluation, etc.
{knowledge_section}
## Workflow
1. **Search knowledge** first — have we learned anything about this problem before?
2. **Plan** your experimental approach (models, features, hyperparameters)
3. For each experiment:
   a. Call `create_experiment` with a clear hypothesis
   b. Write and run code (install packages as needed)
   c. Parse the metrics from stdout
   d. Call `log_metrics` then `complete_experiment` (or `fail_experiment`)
   e. Call `write_knowledge` with what you learned (include experiment_id & domain_id)
4. After 2+ experiments, call `compare_experiments` to assess progress
5. Iterate: try new approaches informed by what you've learned
6. Summarize your findings when you're done

## Important rules
- Always create_experiment BEFORE running code for it
- Always complete_experiment or fail_experiment AFTER — never leave experiments in running state
- Log metrics to the tracking backend for every experiment
- Write knowledge atoms when you discover something meaningful
- Be systematic: change one thing at a time between experiments
- Include print statements in your code to output metrics as JSON
- Always pass experiment_id and domain_id when writing knowledge
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


def _build_domain_section(domain: Domain | None) -> str:
    """Build the domain context section of the system prompt."""
    if domain is None:
        return ""

    lines = [f"\n## Domain: {domain.name}"]
    if domain.description:
        lines.append(domain.description)
    if domain.prompt:
        lines.append(f"\n### Domain steering prompt\n{domain.prompt}")
    if domain.tools:
        lines.append("\n### Domain-specific tools")
        for tool in domain.tools:
            lines.append(f"- **{tool.name}** — {tool.description}")
            if tool.example_usage:
                lines.append(f"  Example usage:\n```python\n{tool.example_usage}\n```")
    if domain.config:
        lines.append(f"\n### Domain configuration\n{domain.config}")
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
