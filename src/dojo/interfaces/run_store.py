"""RunStore interface — persistence for agent runs."""

from abc import ABC, abstractmethod

from dojo.agents.types import AgentRun


class RunStore(ABC):
    """Port for persisting and retrieving agent runs."""

    @abstractmethod
    async def save(self, run: AgentRun) -> str:
        """Persist a run (create or overwrite). Returns the run id."""

    @abstractmethod
    async def load(self, run_id: str) -> AgentRun | None:
        """Load a run by id. Returns None if not found."""

    @abstractmethod
    async def list(self, *, domain_id: str | None = None) -> list[AgentRun]:
        """List all persisted runs, optionally filtered by domain."""

    @abstractmethod
    async def delete(self, run_id: str) -> bool:
        """Delete a run. Returns True if it existed."""
