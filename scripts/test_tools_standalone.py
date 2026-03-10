#!/usr/bin/env python3
"""Standalone test: run a simple ML task with AgentML tools via Claude Agent SDK."""

import asyncio

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    TextBlock,
    ToolUseBlock,
    query,
)

from agentml.api.deps import build_lab
from agentml.config.settings import Settings
from agentml.tools.server import create_agentml_server, get_allowed_tool_names
from agentml.utils.ids import generate_id


async def main():
    # Build lab with default settings (file-based storage in .agentml/)
    settings = Settings.load()
    lab = build_lab(settings)

    # Create our MCP server via the Claude adapter
    server = create_agentml_server(lab)  # defaults to adapter="claude"
    allowed = get_allowed_tool_names(lab)

    task_id = generate_id()

    options = ClaudeAgentOptions(
        mcp_servers={"agentml": server},
        allowed_tools=[
            *allowed,  # All AgentML tools
            "Bash",  # Claude Code built-ins
            "Read",
            "Write",
        ],
        permission_mode="acceptEdits",
        max_turns=30,
    )

    prompt = f"""You are an ML research agent. Your task ID is: {task_id}

Task: Train a simple linear regression on the California Housing dataset and evaluate it.

Steps:
1. Use create_experiment to register what you're doing
2. Write and run Python code (using Bash) to train the model
3. Log the metrics with log_metrics and complete_experiment
4. Write a knowledge atom about what you learned

Use scikit-learn. Keep it simple — this is a validation test."""

    print(f"Starting agent run (task_id={task_id})...\n")

    async for message in query(prompt=prompt, options=options):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    print(f"[Claude] {block.text[:200]}")
                elif isinstance(block, ToolUseBlock):
                    print(f"[Tool] {block.name}({list(block.input.keys())})")
        elif isinstance(message, ResultMessage):
            print(f"\n--- Done in {message.duration_ms}ms, {message.num_turns} turns ---")
            if message.total_cost_usd:
                print(f"Cost: ${message.total_cost_usd:.4f}")

    # Verify results persisted
    experiments = await lab.experiment_store.list(task_id=task_id)
    print(f"\nExperiments stored: {len(experiments)}")
    for exp in experiments:
        print(f"  {exp.id}: {exp.state.value} — {exp.result.metrics if exp.result else '—'}")

    knowledge = await lab.memory_store.list()
    print(f"Knowledge atoms: {len(knowledge)}")
    for atom in knowledge:
        print(f"  {atom.claim[:80]}")


if __name__ == "__main__":
    asyncio.run(main())
