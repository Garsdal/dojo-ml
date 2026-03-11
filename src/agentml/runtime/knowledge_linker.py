"""Knowledge linker — drives the linking/merging/versioning process.

Every knowledge write goes through here. The agent calls
produce_knowledge(finding, experiment_id, domain_id) → linker searches existing
atoms for semantic overlap, merges or creates, links, and versions.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from agentml.core.knowledge import KnowledgeAtom
from agentml.core.knowledge_link import KnowledgeLink, KnowledgeSnapshot, LinkType
from agentml.interfaces.knowledge_link_store import KnowledgeLinkStore
from agentml.interfaces.memory_store import MemoryStore
from agentml.utils.logging import get_logger

logger = get_logger(__name__)

# Minimum keyword overlap ratio to consider a match
_MATCH_THRESHOLD = 0.4
# Minimum number of overlapping words required
_MIN_OVERLAP_WORDS = 3


@dataclass
class LinkingResult:
    """Result of the knowledge linking process."""

    atom_id: str
    action: str  # "created" or "merged"
    version: int
    confidence: float
    merged_with: str | None = None  # ID of the atom merged into, if any


class KnowledgeLinker:
    """Drives the knowledge linking process.

    When an agent produces a finding, the linker:
    1. Searches existing atoms for semantic overlap
    2. If a match is found → merges (updates confidence, version, evidence)
    3. If no match → creates a new atom
    4. Links the atom to the experiment and domain
    5. Records a version snapshot
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

        This is the single entry point for all knowledge creation.
        """
        evidence = evidence_ids or []

        # 1. Search for existing atoms with semantic overlap
        match = await self._find_match(context, claim)

        if match is not None:
            # 2a. Merge with existing atom
            result = await self._merge(
                existing=match,
                context=context,
                claim=claim,
                action=action,
                confidence=confidence,
                evidence_ids=evidence,
                experiment_id=experiment_id,
                domain_id=domain_id,
            )
        else:
            # 2b. Create new atom
            result = await self._create_new(
                context=context,
                claim=claim,
                action=action,
                confidence=confidence,
                evidence_ids=evidence,
                experiment_id=experiment_id,
                domain_id=domain_id,
            )

        logger.info(
            "knowledge_linked",
            atom_id=result.atom_id,
            action=result.action,
            version=result.version,
        )
        return result

    async def _find_match(self, context: str, claim: str) -> KnowledgeAtom | None:
        """Search existing atoms for semantic overlap using keyword matching."""
        query = f"{context} {claim}"
        candidates = await self._memory.search(query, limit=5)

        for candidate in candidates:
            if self._is_semantic_match(context, claim, candidate):
                return candidate

        return None

    def _is_semantic_match(
        self, context: str, claim: str, candidate: KnowledgeAtom
    ) -> bool:
        """Determine if a candidate atom semantically overlaps with the new finding.

        Uses keyword overlap ratio — a simple but effective heuristic.
        """
        new_words = set(f"{context} {claim}".lower().split())
        existing_words = set(f"{candidate.context} {candidate.claim}".lower().split())

        if not new_words or not existing_words:
            return False

        overlap = new_words & existing_words
        # Require minimum number of overlapping words to avoid false matches on short texts
        if len(overlap) < _MIN_OVERLAP_WORDS:
            return False
        # Use the smaller set for ratio to avoid penalizing longer texts
        smaller = min(len(new_words), len(existing_words))
        ratio = len(overlap) / smaller if smaller > 0 else 0.0

        return ratio >= _MATCH_THRESHOLD

    async def _merge(
        self,
        existing: KnowledgeAtom,
        *,
        context: str,
        claim: str,
        action: str,
        confidence: float,
        evidence_ids: list[str],
        experiment_id: str,
        domain_id: str,
    ) -> LinkingResult:
        """Merge a new finding into an existing knowledge atom."""
        old_id = existing.id

        # Create a new versioned atom that supersedes the old one
        new_version = existing.version + 1

        # Average confidence (existing evidence + new evidence)
        merged_confidence = (existing.confidence + confidence) / 2.0

        # Merge evidence IDs (deduplicated)
        merged_evidence = list(set(existing.evidence_ids + evidence_ids))

        # Update the existing atom in place
        existing.version = new_version
        existing.confidence = merged_confidence
        existing.evidence_ids = merged_evidence
        existing.updated_at = datetime.now(UTC)
        # Keep the richer claim (prefer longer/more detailed)
        if len(claim) > len(existing.claim):
            existing.claim = claim
        if action and (not existing.action or len(action) > len(existing.action)):
            existing.action = action

        await self._memory.update(existing)

        # Create link: experiment/domain → atom (updated_by)
        if experiment_id or domain_id:
            link = KnowledgeLink(
                atom_id=existing.id,
                experiment_id=experiment_id or "",
                domain_id=domain_id,
                link_type=LinkType.UPDATED_BY,
            )
            await self._links.link(link)

        # Save version snapshot
        snapshot = KnowledgeSnapshot(
            atom_id=existing.id,
            version=new_version,
            confidence=merged_confidence,
            claim=existing.claim,
            evidence_ids=merged_evidence,
        )
        await self._links.save_snapshot(snapshot)

        return LinkingResult(
            atom_id=existing.id,
            action="merged",
            version=new_version,
            confidence=merged_confidence,
            merged_with=old_id,
        )

    async def _create_new(
        self,
        *,
        context: str,
        claim: str,
        action: str,
        confidence: float,
        evidence_ids: list[str],
        experiment_id: str,
        domain_id: str,
    ) -> LinkingResult:
        """Create a brand-new knowledge atom."""
        atom = KnowledgeAtom(
            context=context,
            claim=claim,
            action=action,
            confidence=confidence,
            evidence_ids=evidence_ids,
            version=1,
        )
        await self._memory.add(atom)

        # Create link: experiment/domain → atom (created_by)
        if experiment_id or domain_id:
            link = KnowledgeLink(
                atom_id=atom.id,
                experiment_id=experiment_id or "",
                domain_id=domain_id,
                link_type=LinkType.CREATED_BY,
            )
            await self._links.link(link)

        # Save initial version snapshot
        snapshot = KnowledgeSnapshot(
            atom_id=atom.id,
            version=1,
            confidence=confidence,
            claim=claim,
            evidence_ids=evidence_ids,
        )
        await self._links.save_snapshot(snapshot)

        return LinkingResult(
            atom_id=atom.id,
            action="created",
            version=1,
            confidence=confidence,
        )

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

    async def get_evolution(self, domain_id: str) -> list[KnowledgeSnapshot]:
        """Get knowledge evolution snapshots for a domain.

        Returns all snapshots for all atoms linked to the domain,
        sorted by timestamp.
        """
        links = await self._links.get_links_for_domain(domain_id)
        atom_ids = {link.atom_id for link in links}

        all_snapshots: list[KnowledgeSnapshot] = []
        for atom_id in atom_ids:
            snapshots = await self._links.get_snapshots(atom_id)
            all_snapshots.extend(snapshots)

        all_snapshots.sort(key=lambda s: s.timestamp)
        return all_snapshots

    async def get_atom_history(self, atom_id: str) -> list[KnowledgeSnapshot]:
        """Get the full version history for a knowledge atom."""
        snapshots = await self._links.get_snapshots(atom_id)
        snapshots.sort(key=lambda s: s.version)
        return snapshots

    async def get_atom_links(self, atom_id: str) -> list[KnowledgeLink]:
        """Get all links for a knowledge atom."""
        return await self._links.get_links_for_atom(atom_id)
