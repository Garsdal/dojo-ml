"""Keyword-overlap knowledge linker — default implementation.

Uses keyword overlap ratio (≥40% of the smaller word set) to find
similar existing atoms. Every finding is stored as a new immutable atom;
similar atoms are linked with RELATED_TO links.
"""

from __future__ import annotations

from agentml.core.knowledge import KnowledgeAtom
from agentml.core.knowledge_link import KnowledgeLink, LinkType
from agentml.interfaces.knowledge_link_store import KnowledgeLinkStore
from agentml.interfaces.knowledge_linker import KnowledgeLinker, LinkingResult
from agentml.interfaces.memory_store import MemoryStore
from agentml.utils.logging import get_logger

logger = get_logger(__name__)

# Minimum keyword overlap ratio to consider a match
_MATCH_THRESHOLD = 0.4
# Minimum number of overlapping words required
_MIN_OVERLAP_WORDS = 3


class KeywordKnowledgeLinker(KnowledgeLinker):
    """Knowledge linker using keyword-overlap heuristic.

    When an agent produces a finding, the linker:
    1. Always creates a new immutable atom
    2. Finds similar existing atoms (keyword overlap)
    3. Creates a CREATED_BY link to the experiment/domain
    4. Creates RELATED_TO links to similar atoms
    """

    def __init__(
        self,
        memory_store: MemoryStore,
        link_store: KnowledgeLinkStore,
    ) -> None:
        self._memory = memory_store
        self._links = link_store

    async def produce_knowledge(
        self,
        *,
        context: str,
        claim: str,
        action: str = "",
        confidence: float = 0.5,
        evidence_ids: list[str] | None = None,
        experiment_id: str = "",
        domain_id: str = "",
    ) -> LinkingResult:
        """Produce a knowledge atom through the linking process.

        Always creates a new immutable atom — never merges.
        """
        evidence = evidence_ids or []

        # 1. Always create a new atom
        atom = KnowledgeAtom(
            context=context,
            claim=claim,
            action=action,
            confidence=confidence,
            evidence_ids=evidence,
            version=1,
        )
        await self._memory.add(atom)

        # 2. Find similar existing atoms (for grouping, not merging)
        similar = await self.find_similar(context, claim, exclude_id=atom.id)

        # 3. Create CREATED_BY link from this atom to the experiment/domain
        if experiment_id or domain_id:
            link = KnowledgeLink(
                atom_id=atom.id,
                experiment_id=experiment_id or "",
                domain_id=domain_id,
                link_type=LinkType.CREATED_BY,
            )
            await self._links.link(link)

        # 4. Create RELATED_TO links to similar atoms
        related_ids: list[str] = []
        for existing in similar:
            rel_link = KnowledgeLink(
                atom_id=atom.id,
                experiment_id=experiment_id or "",
                domain_id=domain_id,
                link_type=LinkType.RELATED_TO,
                related_atom_id=existing.id,
            )
            await self._links.link(rel_link)
            related_ids.append(existing.id)

        logger.info(
            "knowledge_linked",
            atom_id=atom.id,
            action="created",
            related_count=len(related_ids),
        )

        return LinkingResult(
            atom_id=atom.id,
            action="created",
            version=1,
            confidence=confidence,
            related_to=related_ids or None,
        )

    async def find_similar(
        self, context: str, claim: str, *, exclude_id: str = ""
    ) -> list[KnowledgeAtom]:
        """Search existing atoms for semantic overlap using keyword matching."""
        query = f"{context} {claim}"
        candidates = await self._memory.search(query, limit=5)

        matches = []
        for candidate in candidates:
            if candidate.id == exclude_id:
                continue
            if self._is_semantic_match(context, claim, candidate):
                matches.append(candidate)
        return matches

    def _is_semantic_match(self, context: str, claim: str, candidate: KnowledgeAtom) -> bool:
        """Determine if a candidate atom semantically overlaps with the new finding.

        Uses keyword overlap ratio — a simple but effective heuristic.
        """
        new_words = set(f"{context} {claim}".lower().split())
        existing_words = set(f"{candidate.context} {candidate.claim}".lower().split())

        if not new_words or not existing_words:
            return False

        overlap = new_words & existing_words
        if len(overlap) < _MIN_OVERLAP_WORDS:
            return False
        smaller = min(len(new_words), len(existing_words))
        ratio = len(overlap) / smaller if smaller > 0 else 0.0

        return ratio >= _MATCH_THRESHOLD

    async def get_domain_knowledge(self, domain_id: str) -> list[KnowledgeAtom]:
        """Get all knowledge atoms linked to a domain."""
        links = await self._links.get_links_for_domain(domain_id)
        atom_ids = {link.atom_id for link in links}

        atoms = []
        for atom_id in atom_ids:
            atom = await self._memory.get(atom_id)
            if atom is not None:
                atoms.append(atom)
        return atoms

    async def get_atom_links(self, atom_id: str) -> list[KnowledgeLink]:
        """Get all links for a knowledge atom."""
        return await self._links.get_links_for_atom(atom_id)
