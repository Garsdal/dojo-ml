"""Memory store interface for knowledge atoms."""

from abc import ABC, abstractmethod

from agentml.core.knowledge import KnowledgeAtom


class MemoryStore(ABC):
    """Abstract base class for knowledge atom persistence and search."""

    @abstractmethod
    async def add(self, atom: KnowledgeAtom) -> str:
        """Add a knowledge atom.

        Args:
            atom: The knowledge atom to add.

        Returns:
            The atom ID.
        """
        ...

    @abstractmethod
    async def search(self, query: str, *, limit: int = 10) -> list[KnowledgeAtom]:
        """Search for relevant knowledge atoms.

        Args:
            query: The search query.
            limit: Maximum number of results.

        Returns:
            A list of matching knowledge atoms.
        """
        ...

    @abstractmethod
    async def list(self) -> list[KnowledgeAtom]:
        """List all knowledge atoms.

        Returns:
            A list of all atoms.
        """
        ...

    @abstractmethod
    async def delete(self, atom_id: str) -> bool:
        """Delete a knowledge atom.

        Args:
            atom_id: The atom ID.

        Returns:
            True if deleted, False if not found.
        """
        ...

    async def get(self, atom_id: str) -> KnowledgeAtom | None:
        """Get a single knowledge atom by ID.

        Default implementation searches all atoms. Override for efficiency.
        """
        for atom in await self.list():
            if atom.id == atom_id:
                return atom
        return None

    async def update(self, atom: KnowledgeAtom) -> str:
        """Update an existing knowledge atom.

        Default implementation deletes and re-adds. Override for efficiency.
        """
        await self.delete(atom.id)
        return await self.add(atom)
