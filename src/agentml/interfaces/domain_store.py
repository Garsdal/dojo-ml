"""Domain store interface."""

from abc import ABC, abstractmethod

from agentml.core.domain import Domain


class DomainStore(ABC):
    """Abstract base class for domain persistence."""

    @abstractmethod
    async def save(self, domain: Domain) -> str: ...

    @abstractmethod
    async def load(self, domain_id: str) -> Domain | None: ...

    @abstractmethod
    async def list(self) -> list[Domain]: ...

    @abstractmethod
    async def delete(self, domain_id: str) -> bool: ...

    @abstractmethod
    async def update(self, domain: Domain) -> str: ...
