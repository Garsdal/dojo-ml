"""Domains router — CRUD + tool management for research domains."""

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from agentml.core.domain import Domain, DomainStatus, DomainTool, ToolType
from agentml.runtime.domain_service import DomainService
from agentml.runtime.lab import LabEnvironment
from agentml.tools.tool_generation import (
    build_tool_generation_prompt,
    parse_generated_tools,
)

router = APIRouter(prefix="/domains", tags=["domains"])


def _get_lab(request: Request) -> LabEnvironment:
    return request.app.state.lab


# --- Request / Response models ---


class DomainToolRequest(BaseModel):
    name: str
    description: str = ""
    type: str = "custom"
    example_usage: str = ""
    parameters: dict[str, Any] = {}
    created_by: str = "human"


class DomainToolResponse(BaseModel):
    id: str
    name: str
    description: str
    type: str
    example_usage: str
    parameters: dict[str, Any]
    created_by: str
    created_at: str


class CreateDomainRequest(BaseModel):
    name: str
    description: str = ""
    prompt: str = ""
    config: dict[str, Any] = {}
    metadata: dict[str, Any] = {}
    tools: list[DomainToolRequest] = []


class UpdateDomainRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    prompt: str | None = None
    status: str | None = None
    config: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None


class DomainResponse(BaseModel):
    id: str
    name: str
    description: str
    prompt: str
    status: str
    config: dict[str, Any]
    metadata: dict[str, Any]
    experiment_ids: list[str]
    tools: list[DomainToolResponse]
    created_at: str
    updated_at: str


def _tool_response(tool: DomainTool) -> DomainToolResponse:
    return DomainToolResponse(
        id=tool.id,
        name=tool.name,
        description=tool.description,
        type=tool.type.value,
        example_usage=tool.example_usage,
        parameters=tool.parameters,
        created_by=tool.created_by,
        created_at=tool.created_at.isoformat(),
    )


def _domain_response(domain: Domain) -> DomainResponse:
    return DomainResponse(
        id=domain.id,
        name=domain.name,
        description=domain.description,
        prompt=domain.prompt,
        status=domain.status.value,
        config=domain.config,
        metadata=domain.metadata,
        experiment_ids=domain.experiment_ids,
        tools=[_tool_response(t) for t in domain.tools],
        created_at=domain.created_at.isoformat(),
        updated_at=domain.updated_at.isoformat(),
    )


# --- Domain CRUD ---


@router.post("", response_model=DomainResponse, status_code=201)
async def create_domain(body: CreateDomainRequest, request: Request) -> DomainResponse:
    lab = _get_lab(request)
    service = DomainService(lab)

    tools = [
        DomainTool(
            name=t.name,
            description=t.description,
            type=ToolType(t.type),
            example_usage=t.example_usage,
            parameters=t.parameters,
            created_by=t.created_by,
        )
        for t in body.tools
    ]

    domain = Domain(
        name=body.name,
        description=body.description,
        prompt=body.prompt,
        status=DomainStatus.ACTIVE,
        config=body.config,
        metadata=body.metadata,
        tools=tools,
    )
    await service.create(domain)
    return _domain_response(domain)


@router.get("", response_model=list[DomainResponse])
async def list_domains(request: Request) -> list[DomainResponse]:
    lab = _get_lab(request)
    service = DomainService(lab)
    domains = await service.list()
    return [_domain_response(d) for d in domains]


@router.get("/{domain_id}", response_model=DomainResponse)
async def get_domain(domain_id: str, request: Request) -> DomainResponse:
    lab = _get_lab(request)
    service = DomainService(lab)
    domain = await service.get(domain_id)
    if domain is None:
        raise HTTPException(status_code=404, detail="Domain not found")
    return _domain_response(domain)


@router.put("/{domain_id}", response_model=DomainResponse)
async def update_domain(
    domain_id: str, body: UpdateDomainRequest, request: Request
) -> DomainResponse:
    lab = _get_lab(request)
    service = DomainService(lab)
    domain = await service.get(domain_id)
    if domain is None:
        raise HTTPException(status_code=404, detail="Domain not found")

    if body.name is not None:
        domain.name = body.name
    if body.description is not None:
        domain.description = body.description
    if body.prompt is not None:
        domain.prompt = body.prompt
    if body.status is not None:
        domain.status = DomainStatus(body.status)
    if body.config is not None:
        domain.config = body.config
    if body.metadata is not None:
        domain.metadata = body.metadata

    await service.update(domain)
    return _domain_response(domain)


@router.delete("/{domain_id}", status_code=204)
async def delete_domain(domain_id: str, request: Request) -> None:
    lab = _get_lab(request)
    service = DomainService(lab)
    deleted = await service.delete(domain_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Domain not found")


# --- Domain Tools ---


@router.post("/{domain_id}/tools", response_model=DomainToolResponse, status_code=201)
async def add_domain_tool(
    domain_id: str, body: DomainToolRequest, request: Request
) -> DomainToolResponse:
    lab = _get_lab(request)
    service = DomainService(lab)

    tool = DomainTool(
        name=body.name,
        description=body.description,
        type=ToolType(body.type),
        example_usage=body.example_usage,
        parameters=body.parameters,
        created_by=body.created_by,
    )
    await service.add_tool(domain_id, tool)
    return _tool_response(tool)


@router.get("/{domain_id}/tools", response_model=list[DomainToolResponse])
async def list_domain_tools(domain_id: str, request: Request) -> list[DomainToolResponse]:
    lab = _get_lab(request)
    service = DomainService(lab)
    domain = await service.get(domain_id)
    if domain is None:
        raise HTTPException(status_code=404, detail="Domain not found")
    return [_tool_response(t) for t in domain.tools]


@router.delete("/{domain_id}/tools/{tool_id}", status_code=204)
async def remove_domain_tool(domain_id: str, tool_id: str, request: Request) -> None:
    lab = _get_lab(request)
    service = DomainService(lab)
    try:
        await service.remove_tool(domain_id, tool_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Domain not found") from exc


# --- Domain Experiments ---


@router.get("/{domain_id}/experiments")
async def list_domain_experiments(domain_id: str, request: Request) -> list[dict]:
    lab = _get_lab(request)
    experiments = await lab.experiment_store.list(domain_id=domain_id)
    return [
        {
            "id": exp.id,
            "domain_id": exp.domain_id,
            "state": exp.state.value,
            "hypothesis": exp.hypothesis.description if exp.hypothesis else None,
            "config": exp.config,
            "metrics": exp.result.metrics if exp.result else None,
            "error": exp.result.error if exp.result else None,
            "created_at": exp.created_at.isoformat(),
        }
        for exp in experiments
    ]


# --- Domain Metrics Evolution ---


@router.get("/{domain_id}/metrics")
async def domain_metrics_evolution(domain_id: str, request: Request) -> dict:
    """Aggregate metrics across all experiments in a domain."""
    lab = _get_lab(request)
    experiments = await lab.experiment_store.list(domain_id=domain_id)

    metrics_over_time = []
    for exp in sorted(experiments, key=lambda e: e.created_at):
        if exp.result and exp.result.metrics:
            metrics_over_time.append(
                {
                    "experiment_id": exp.id,
                    "timestamp": exp.created_at.isoformat(),
                    "metrics": exp.result.metrics,
                }
            )

    return {"domain_id": domain_id, "metrics_evolution": metrics_over_time}


# --- Domain Knowledge ---


@router.get("/{domain_id}/knowledge")
async def list_domain_knowledge(domain_id: str, request: Request) -> list[dict]:
    """All knowledge atoms linked to a domain."""
    lab = _get_lab(request)

    atoms = await lab.knowledge_linker.get_domain_knowledge(domain_id)
    return [
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


# --- AI Tool Generation ---


class GenerateToolsRequest(BaseModel):
    hint: str = ""


class GeneratedToolResponse(BaseModel):
    name: str
    description: str
    type: str
    example_usage: str
    parameters: dict[str, Any]


class GenerateToolsResponse(BaseModel):
    domain_id: str
    generated: list[GeneratedToolResponse]
    prompt_used: str
    raw_output: str | None = None


@router.post("/{domain_id}/tools/generate", response_model=GenerateToolsResponse)
async def generate_tools(
    domain_id: str, body: GenerateToolsRequest, request: Request
) -> GenerateToolsResponse:
    """AI-generate tool definitions for a domain.

    Returns the generated tools for review. They are NOT automatically
    registered — the client should review and then POST individual tools
    to ``/domains/{id}/tools`` to register them.
    """
    lab = _get_lab(request)
    service = DomainService(lab)
    domain = await service.get(domain_id)
    if domain is None:
        raise HTTPException(status_code=404, detail="Domain not found")

    prompt = build_tool_generation_prompt(domain, hint=body.hint)

    # Try using the configured agent backend to generate tools
    from agentml.agents.factory import create_agent_backend

    backend = create_agent_backend(lab.settings)

    # Use the backend to get a completion
    # For backends that support direct completion, use that.
    # Otherwise, return the prompt for manual generation.
    try:
        raw_output = await backend.complete(prompt)
    except (AttributeError, NotImplementedError):
        # Backend doesn't support direct completion
        return GenerateToolsResponse(
            domain_id=domain_id,
            generated=[],
            prompt_used=prompt,
            raw_output=None,
        )

    try:
        tool_dicts = parse_generated_tools(raw_output)
    except ValueError as e:
        raise HTTPException(
            status_code=422,
            detail=f"Failed to parse generated tools: {e}",
        ) from e

    return GenerateToolsResponse(
        domain_id=domain_id,
        generated=[
            GeneratedToolResponse(
                name=t["name"],
                description=t["description"],
                type=t["type"],
                example_usage=t["example_usage"],
                parameters=t["parameters"],
            )
            for t in tool_dicts
        ],
        prompt_used=prompt,
        raw_output=raw_output,
    )
