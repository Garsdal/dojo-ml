"""Knowledge link store interface."""

from abc import ABC, abstractmethod

from agentml.core.knowledge_link import KnowledgeLink


class KnowledgeLinkStore(ABC):
    """Abstract base class for knowledge link persistence."""

    @abstractmethod
    async def link(self, link: KnowledgeLink) -> str:
        """Create a link between an atom and an experiment/domain."""
        ...

    @abstractmethod
    async def unlink(self, link_id: str) -> bool:
        """Remove a link."""
        ...

    @abstractmethod
    async def get_links_for_atom(self, atom_id: str) -> list[KnowledgeLink]:
        """Get all links for a knowledge atom."""
        ...

    @abstractmethod
    async def get_links_for_experiment(self, experiment_id: str) -> list[KnowledgeLink]:
        """Get all links for an experiment."""
        ...

    @abstractmethod
    async def get_links_for_domain(self, domain_id: str) -> list[KnowledgeLink]:
        """Get all links for a domain."""
        ...
