"""Knowledge router — query knowledge atoms, version history, and evolution."""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from agentml.core.knowledge import KnowledgeAtom
from agentml.runtime.knowledge_linker import KnowledgeLinker
from agentml.runtime.lab import LabEnvironment

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


def _get_lab(request: Request) -> LabEnvironment:
    return request.app.state.lab


def _get_linker(lab: LabEnvironment) -> KnowledgeLinker | None:
    if lab.knowledge_link_store is not None:
        return KnowledgeLinker(lab.memory_store, lab.knowledge_link_store)
    return None


class KnowledgeResponse(BaseModel):
    """API response for a knowledge atom."""

    id: str
    context: str
    claim: str
    action: str
    confidence: float
    evidence_ids: list[str] = []
    version: int = 1
    supersedes: str | None = None


class KnowledgeLinkResponse(BaseModel):
    """API response for a knowledge link."""

    id: str
    atom_id: str
    experiment_id: str
    domain_id: str
    link_type: str


class KnowledgeSnapshotResponse(BaseModel):
    """API response for a knowledge snapshot."""

    id: str
    atom_id: str
    version: int
    confidence: float
    claim: str
    evidence_ids: list[str] = []
    timestamp: str


class KnowledgeDetailResponse(BaseModel):
    """Detailed atom response with links and history."""

    atom: KnowledgeResponse
    links: list[KnowledgeLinkResponse] = []
    history: list[KnowledgeSnapshotResponse] = []


def _atom_to_response(atom: KnowledgeAtom) -> KnowledgeResponse:
    return KnowledgeResponse(
        id=atom.id,
        context=atom.context,
        claim=atom.claim,
        action=atom.action,
        confidence=atom.confidence,
        evidence_ids=atom.evidence_ids,
        version=atom.version,
        supersedes=atom.supersedes,
    )


@router.get("", response_model=list[KnowledgeResponse])
async def list_knowledge(request: Request, domain_id: str | None = None) -> list[KnowledgeResponse]:
    """List all knowledge atoms, optionally filtered by domain."""
    lab = _get_lab(request)

    if domain_id:
        linker = _get_linker(lab)
        if linker is not None:
            atoms = await linker.get_domain_knowledge(domain_id)
            return [_atom_to_response(a) for a in atoms]

    atoms = await lab.memory_store.list()
    return [_atom_to_response(a) for a in atoms]


@router.get("/relevant", response_model=list[KnowledgeResponse])
async def search_knowledge(
    request: Request,
    query: str = "",
    limit: int = 10,
    domain_id: str | None = None,
) -> list[KnowledgeResponse]:
    """Search for relevant knowledge atoms, optionally scoped to a domain."""
    lab = _get_lab(request)

    if domain_id:
        linker = _get_linker(lab)
        if linker is not None:
            atoms = await linker.get_domain_knowledge(domain_id)
            # Apply keyword filter within domain knowledge
            if query:
                query_lower = query.lower()
                keywords = query_lower.split()
                atoms = [
                    a
                    for a in atoms
                    if any(kw in f"{a.context} {a.claim} {a.action}".lower() for kw in keywords)
                ]
            return [_atom_to_response(a) for a in atoms[:limit]]

    atoms = await lab.memory_store.search(query, limit=limit)
    return [_atom_to_response(a) for a in atoms]


@router.get("/{atom_id}", response_model=KnowledgeDetailResponse)
async def get_knowledge(atom_id: str, request: Request) -> KnowledgeDetailResponse:
    """Get a knowledge atom with full version history and links."""
    lab = _get_lab(request)
    atom = await lab.memory_store.get(atom_id)
    if atom is None:
        raise HTTPException(status_code=404, detail="Knowledge atom not found")

    linker = _get_linker(lab)
    links: list[KnowledgeLinkResponse] = []
    history: list[KnowledgeSnapshotResponse] = []

    if linker is not None:
        raw_links = await linker.get_atom_links(atom_id)
        links = [
            KnowledgeLinkResponse(
                id=lnk.id,
                atom_id=lnk.atom_id,
                experiment_id=lnk.experiment_id,
                domain_id=lnk.domain_id,
                link_type=lnk.link_type.value,
            )
            for lnk in raw_links
        ]
        raw_history = await linker.get_atom_history(atom_id)
        history = [
            KnowledgeSnapshotResponse(
                id=snap.id,
                atom_id=snap.atom_id,
                version=snap.version,
                confidence=snap.confidence,
                claim=snap.claim,
                evidence_ids=snap.evidence_ids,
                timestamp=snap.timestamp.isoformat(),
            )
            for snap in raw_history
        ]

    return KnowledgeDetailResponse(
        atom=_atom_to_response(atom),
        links=links,
        history=history,
    )


@router.get("/{atom_id}/history", response_model=list[KnowledgeSnapshotResponse])
async def get_knowledge_history(atom_id: str, request: Request) -> list[KnowledgeSnapshotResponse]:
    """Get version history for a knowledge atom."""
    lab = _get_lab(request)
    linker = _get_linker(lab)
    if linker is None:
        return []

    snapshots = await linker.get_atom_history(atom_id)
    return [
        KnowledgeSnapshotResponse(
            id=snap.id,
            atom_id=snap.atom_id,
            version=snap.version,
            confidence=snap.confidence,
            claim=snap.claim,
            evidence_ids=snap.evidence_ids,
            timestamp=snap.timestamp.isoformat(),
        )
        for snap in snapshots
    ]


class CreateKnowledgeRequest(BaseModel):
    """Request body for creating a knowledge atom (goes through linker)."""

    context: str
    claim: str
    action: str = ""
    confidence: float = 0.5
    evidence_ids: list[str] = []
    experiment_id: str = ""
    domain_id: str = ""


class LinkingResultResponse(BaseModel):
    """Response from knowledge creation through the linker."""

    atom_id: str
    action: str  # "created" or "merged"
    version: int
    confidence: float
    merged_with: str | None = None


@router.post("", response_model=LinkingResultResponse, status_code=201)
async def create_knowledge(body: CreateKnowledgeRequest, request: Request) -> LinkingResultResponse:
    """Create a new knowledge atom (goes through the knowledge linker)."""
    lab = _get_lab(request)
    linker = _get_linker(lab)

    if linker is not None:
        result = await linker.produce_knowledge(
            context=body.context,
            claim=body.claim,
            action=body.action,
            confidence=body.confidence,
            evidence_ids=body.evidence_ids,
            experiment_id=body.experiment_id,
            domain_id=body.domain_id,
        )
        return LinkingResultResponse(
            atom_id=result.atom_id,
            action=result.action,
            version=result.version,
            confidence=result.confidence,
            merged_with=result.merged_with,
        )

    # Fallback: direct write (no linker)
    atom = KnowledgeAtom(
        context=body.context,
        claim=body.claim,
        action=body.action,
        confidence=body.confidence,
        evidence_ids=body.evidence_ids,
    )
    await lab.memory_store.add(atom)
    return LinkingResultResponse(
        atom_id=atom.id,
        action="created",
        version=1,
        confidence=atom.confidence,
    )


@router.delete("/{atom_id}", status_code=204)
async def delete_knowledge(atom_id: str, request: Request) -> None:
    """Delete a knowledge atom by ID."""
    lab = _get_lab(request)
    deleted = await lab.memory_store.delete(atom_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Knowledge atom not found")
