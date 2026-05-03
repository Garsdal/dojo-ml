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

    @abstractmethod
    async def request_stop(self, run_id: str) -> None:
        """Drop a stop-signal sentinel that an active orchestrator can poll.

        Cross-process signalling for the foreground ``dojo run`` case: the
        process running ``execute()`` polls ``is_stop_requested`` and triggers
        a graceful interrupt when the sentinel appears.
        """

    @abstractmethod
    async def is_stop_requested(self, run_id: str) -> bool:
        """True iff a stop signal has been raised for this run."""

    @abstractmethod
    async def clear_stop_request(self, run_id: str) -> None:
        """Remove the stop-signal sentinel (called once it's been honoured)."""
