"""AgentML knowledge management tools."""

from typing import Any

from agentml.runtime.knowledge_linker import KnowledgeLinker
from agentml.runtime.lab import LabEnvironment
from agentml.tools.base import ToolDef, ToolResult


def _get_linker(lab: LabEnvironment) -> KnowledgeLinker | None:
    """Build a KnowledgeLinker if link store is available."""
    if lab.knowledge_link_store is not None:
        return KnowledgeLinker(lab.memory_store, lab.knowledge_link_store)
    return None


def create_knowledge_tools(lab: LabEnvironment) -> list[ToolDef]:
    """Create all knowledge tools backed by a LabEnvironment."""

    async def write_knowledge(args: dict[str, Any]) -> ToolResult:
        linker = _get_linker(lab)
        if linker is not None:
            # Route through KnowledgeLinker for mandatory linking/merging
            result = await linker.produce_knowledge(
                context=args["context"],
                claim=args["claim"],
                action=args.get("action", ""),
                confidence=args.get("confidence", 0.5),
                evidence_ids=args.get("evidence_ids", []),
                experiment_id=args.get("experiment_id", ""),
                domain_id=args.get("domain_id", ""),
            )
            return ToolResult(
                data={
                    "atom_id": result.atom_id,
                    "action": result.action,
                    "version": result.version,
                    "confidence": result.confidence,
                    "merged_with": result.merged_with,
                }
            )
        # Fallback: direct write (no linking infrastructure)
        from agentml.core.knowledge import KnowledgeAtom

        atom = KnowledgeAtom(
            context=args["context"],
            claim=args["claim"],
            action=args.get("action", ""),
            confidence=args.get("confidence", 0.0),
            evidence_ids=args.get("evidence_ids", []),
        )
        atom_id = await lab.memory_store.add(atom)
        return ToolResult(data={"atom_id": atom_id, "action": "created", "version": 1})

    async def search_knowledge(args: dict[str, Any]) -> ToolResult:
        domain_id = args.get("domain_id")
        linker = _get_linker(lab)

        # If domain_id is specified and linker is available, use domain-scoped search
        if domain_id and linker is not None:
            atoms = await linker.get_domain_knowledge(domain_id)
            # Apply keyword filter within domain knowledge
            query = args.get("query", "")
            if query:
                query_lower = query.lower()
                keywords = query_lower.split()
                atoms = [
                    a
                    for a in atoms
                    if any(kw in f"{a.context} {a.claim} {a.action}".lower() for kw in keywords)
                ]
            atoms = atoms[: args.get("limit", 10)]
        else:
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
                    "version": a.version,
                }
                for a in atoms
            ]
        )

    async def list_knowledge(args: dict[str, Any]) -> ToolResult:
        domain_id = args.get("domain_id")
        linker = _get_linker(lab)

        if domain_id and linker is not None:
            atoms = await linker.get_domain_knowledge(domain_id)
        else:
            atoms = await lab.memory_store.list()

        return ToolResult(
            data=[
                {
                    "id": a.id,
                    "context": a.context,
                    "claim": a.claim,
                    "action": a.action,
                    "confidence": a.confidence,
                    "version": a.version,
                }
                for a in atoms
            ]
        )

    return [
        ToolDef(
            name="write_knowledge",
            description=(
                "Record a learning or insight from your experiments as a knowledge "
                "atom. This goes through the knowledge linker — if a similar finding "
                "already exists, it will be merged (increasing confidence and version). "
                "If not, a new atom is created. Always do this after experiments."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "context": {
                        "type": "string",
                        "description": "What situation/experiment this learning comes from",
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
                    "experiment_id": {
                        "type": "string",
                        "description": "The experiment that produced this finding",
                    },
                    "domain_id": {
                        "type": "string",
                        "description": "The domain this knowledge belongs to",
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
                "Use this to recall prior learnings before starting a new experiment. "
                "Optionally filter by domain_id for domain-scoped search."
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
                    "domain_id": {
                        "type": "string",
                        "description": "Optional: filter to knowledge linked to this domain",
                    },
                },
                "required": ["query"],
            },
            handler=search_knowledge,
        ),
        ToolDef(
            name="list_knowledge",
            description=(
                "List all recorded knowledge atoms. "
                "Optionally filter by domain_id for domain-scoped listing."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "domain_id": {
                        "type": "string",
                        "description": "Optional: filter to knowledge linked to this domain",
                    },
                },
            },
            handler=list_knowledge,
        ),
    ]
