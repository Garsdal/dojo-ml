"""Knowledge router — query knowledge atoms."""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from agentml.core.knowledge import KnowledgeAtom
from agentml.runtime.lab import LabEnvironment

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


def _get_lab(request: Request) -> LabEnvironment:
    return request.app.state.lab


class KnowledgeResponse(BaseModel):
    """API response for a knowledge atom."""

    id: str
    context: str
    claim: str
    action: str
    confidence: float
    evidence_ids: list[str] = []


@router.get("", response_model=list[KnowledgeResponse])
async def list_knowledge(request: Request) -> list[KnowledgeResponse]:
    """List all knowledge atoms."""
    lab = _get_lab(request)
    atoms = await lab.memory_store.list()
    return [
        KnowledgeResponse(
            id=atom.id,
            context=atom.context,
            claim=atom.claim,
            action=atom.action,
            confidence=atom.confidence,
            evidence_ids=atom.evidence_ids,
        )
        for atom in atoms
    ]


@router.get("/relevant", response_model=list[KnowledgeResponse])
async def search_knowledge(
    request: Request, query: str = "", limit: int = 10
) -> list[KnowledgeResponse]:
    """Search for relevant knowledge atoms."""
    lab = _get_lab(request)
    atoms = await lab.memory_store.search(query, limit=limit)
    return [
        KnowledgeResponse(
            id=atom.id,
            context=atom.context,
            claim=atom.claim,
            action=atom.action,
            confidence=atom.confidence,
            evidence_ids=atom.evidence_ids,
        )
        for atom in atoms
    ]


class CreateKnowledgeRequest(BaseModel):
    """Request body for creating a knowledge atom."""

    context: str
    claim: str
    action: str = ""
    confidence: float = 0.5
    evidence_ids: list[str] = []


@router.post("", response_model=KnowledgeResponse, status_code=201)
async def create_knowledge(body: CreateKnowledgeRequest, request: Request) -> KnowledgeResponse:
    """Create a new knowledge atom."""
    lab = _get_lab(request)
    atom = KnowledgeAtom(
        context=body.context,
        claim=body.claim,
        action=body.action,
        confidence=body.confidence,
        evidence_ids=body.evidence_ids,
    )
    await lab.memory_store.add(atom)
    return KnowledgeResponse(
        id=atom.id,
        context=atom.context,
        claim=atom.claim,
        action=atom.action,
        confidence=atom.confidence,
        evidence_ids=atom.evidence_ids,
    )


@router.delete("/{atom_id}", status_code=204)
async def delete_knowledge(atom_id: str, request: Request) -> None:
    """Delete a knowledge atom by ID."""
    lab = _get_lab(request)
    deleted = await lab.memory_store.delete(atom_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Knowledge atom not found")
