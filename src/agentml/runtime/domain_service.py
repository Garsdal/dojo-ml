"""Domain service — orchestrates domain lifecycle."""

from datetime import UTC, datetime

from agentml.core.domain import Domain, DomainStatus, DomainTool
from agentml.runtime.lab import LabEnvironment
from agentml.utils.logging import get_logger

logger = get_logger(__name__)


class DomainService:
    """CRUD + tool management for domains."""

    def __init__(self, lab: LabEnvironment) -> None:
        self.lab = lab

    async def create(self, domain: Domain) -> str:
        """Create a new domain."""
        domain_id = await self.lab.domain_store.save(domain)
        logger.info("domain_created", domain_id=domain_id, name=domain.name)
        return domain_id

    async def get(self, domain_id: str) -> Domain | None:
        """Get a domain by ID."""
        return await self.lab.domain_store.load(domain_id)

    async def list(self) -> list[Domain]:
        """List all domains."""
        return await self.lab.domain_store.list()

    async def update(self, domain: Domain) -> str:
        """Update an existing domain."""
        domain.updated_at = datetime.now(UTC)
        await self.lab.domain_store.update(domain)
        logger.info("domain_updated", domain_id=domain.id)
        return domain.id

    async def delete(self, domain_id: str) -> bool:
        """Delete a domain."""
        deleted = await self.lab.domain_store.delete(domain_id)
        if deleted:
            logger.info("domain_deleted", domain_id=domain_id)
        return deleted

    async def activate(self, domain_id: str) -> Domain:
        """Set domain status to ACTIVE."""
        domain = await self.get(domain_id)
        if domain is None:
            raise ValueError(f"Domain not found: {domain_id}")
        domain.status = DomainStatus.ACTIVE
        domain.updated_at = datetime.now(UTC)
        await self.lab.domain_store.update(domain)
        return domain

    async def add_tool(self, domain_id: str, tool: DomainTool) -> Domain:
        """Add a tool to a domain."""
        domain = await self.get(domain_id)
        if domain is None:
            raise ValueError(f"Domain not found: {domain_id}")
        domain.tools.append(tool)
        domain.updated_at = datetime.now(UTC)
        await self.lab.domain_store.update(domain)
        logger.info("domain_tool_added", domain_id=domain_id, tool_name=tool.name)
        return domain

    async def remove_tool(self, domain_id: str, tool_id: str) -> Domain:
        """Remove a tool from a domain."""
        domain = await self.get(domain_id)
        if domain is None:
            raise ValueError(f"Domain not found: {domain_id}")
        domain.tools = [t for t in domain.tools if t.id != tool_id]
        domain.updated_at = datetime.now(UTC)
        await self.lab.domain_store.update(domain)
        logger.info("domain_tool_removed", domain_id=domain_id, tool_id=tool_id)
        return domain
