"""AgentML knowledge management tools."""

from typing import Any

from agentml.core.knowledge import KnowledgeAtom
from agentml.runtime.lab import LabEnvironment
from agentml.tools.base import ToolDef, ToolResult


def create_knowledge_tools(lab: LabEnvironment) -> list[ToolDef]:
    """Create all knowledge tools backed by a LabEnvironment."""

    async def write_knowledge(args: dict[str, Any]) -> ToolResult:
        atom = KnowledgeAtom(
            context=args["context"],
            claim=args["claim"],
            action=args.get("action", ""),
            confidence=args.get("confidence", 0.0),
            evidence_ids=args.get("evidence_ids", []),
        )
        atom_id = await lab.memory_store.add(atom)
        return ToolResult(data={"atom_id": atom_id, "status": "saved"})

    async def search_knowledge(args: dict[str, Any]) -> ToolResult:
        atoms = await lab.memory_store.search(args["query"], limit=args.get("limit", 10))
        return ToolResult(
            data=[
                {
                    "id": a.id,
                    "context": a.context,
                    "claim": a.claim,
                    "action": a.action,
                    "confidence": a.confidence,
                    "evidence_ids": a.evidence_ids,
                }
                for a in atoms
            ]
        )

    async def list_knowledge(args: dict[str, Any]) -> ToolResult:
        atoms = await lab.memory_store.list()
        return ToolResult(
            data=[
                {
                    "id": a.id,
                    "context": a.context,
                    "claim": a.claim,
                    "action": a.action,
                    "confidence": a.confidence,
                }
                for a in atoms
            ]
        )

    return [
        ToolDef(
            name="write_knowledge",
            description=(
                "Record a learning or insight from your experiments as a knowledge "
                "atom. Do this whenever you discover something meaningful — model "
                "comparisons, feature importance findings, hyperparameter effects, etc."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "context": {
                        "type": "string",
                        "description": ("What situation/experiment this learning comes from"),
                    },
                    "claim": {
                        "type": "string",
                        "description": "The factual claim or finding",
                    },
                    "action": {
                        "type": "string",
                        "description": "Recommended action based on this finding",
                    },
                    "confidence": {
                        "type": "number",
                        "description": "Confidence 0.0-1.0",
                    },
                    "evidence_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Experiment IDs that support this claim",
                    },
                },
                "required": ["context", "claim"],
            },
            handler=write_knowledge,
        ),
        ToolDef(
            name="search_knowledge",
            description=(
                "Search for previously recorded knowledge atoms relevant to a query. "
                "Use this to recall prior learnings before starting a new experiment."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "What to search for",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max results (default 10)",
                    },
                },
                "required": ["query"],
            },
            handler=search_knowledge,
        ),
        ToolDef(
            name="list_knowledge",
            description="List all recorded knowledge atoms.",
            parameters={"type": "object", "properties": {}},
            handler=list_knowledge,
        ),
    ]
