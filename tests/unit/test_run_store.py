"""Unit tests for LocalRunStore — disk persistence of AgentRuns."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from dojo.agents.types import AgentEvent, AgentRun, AgentRunResult, RunStatus
from dojo.storage.local.run import LocalRunStore


@pytest.fixture
def store(tmp_path: Path) -> LocalRunStore:
    return LocalRunStore(base_dir=tmp_path / "runs")


async def test_save_and_load(store: LocalRunStore) -> None:
    run = AgentRun(domain_id="d1", prompt="hello", status=RunStatus.RUNNING)
    await store.save(run)
    loaded = await store.load(run.id)
    assert loaded is not None
    assert loaded.id == run.id
    assert loaded.domain_id == "d1"
    assert loaded.prompt == "hello"
    assert loaded.status == RunStatus.RUNNING


async def test_load_nonexistent_returns_none(store: LocalRunStore) -> None:
    assert await store.load("no-such-id") is None


async def test_save_overwrites(store: LocalRunStore) -> None:
    run = AgentRun(domain_id="d1", prompt="p", status=RunStatus.RUNNING)
    await store.save(run)
    run.status = RunStatus.COMPLETED
    run.completed_at = datetime.now(UTC)
    await store.save(run)
    loaded = await store.load(run.id)
    assert loaded is not None
    assert loaded.status == RunStatus.COMPLETED
    assert loaded.completed_at is not None


async def test_events_round_trip(store: LocalRunStore) -> None:
    run = AgentRun(domain_id="d1", prompt="p")
    run.events = [
        AgentEvent(event_type="text", data={"text": "hello"}),
        AgentEvent(event_type="tool_call", data={"tool": "create_experiment"}),
    ]
    await store.save(run)
    loaded = await store.load(run.id)
    assert loaded is not None
    assert len(loaded.events) == 2
    assert loaded.events[0].event_type == "text"
    assert loaded.events[1].data["tool"] == "create_experiment"


async def test_result_round_trip(store: LocalRunStore) -> None:
    run = AgentRun(domain_id="d1", prompt="p", status=RunStatus.COMPLETED)
    run.result = AgentRunResult(num_turns=5, total_cost_usd=0.12, is_error=False)
    await store.save(run)
    loaded = await store.load(run.id)
    assert loaded is not None
    assert loaded.result is not None
    assert loaded.result.num_turns == 5
    assert loaded.result.total_cost_usd == pytest.approx(0.12)


async def test_list_all(store: LocalRunStore) -> None:
    r1 = AgentRun(domain_id="d1", prompt="a")
    r2 = AgentRun(domain_id="d2", prompt="b")
    await store.save(r1)
    await store.save(r2)
    runs = await store.list()
    assert {r.id for r in runs} == {r1.id, r2.id}


async def test_list_domain_filter(store: LocalRunStore) -> None:
    r1 = AgentRun(domain_id="d1", prompt="a")
    r2 = AgentRun(domain_id="d2", prompt="b")
    await store.save(r1)
    await store.save(r2)
    runs = await store.list(domain_id="d1")
    assert len(runs) == 1
    assert runs[0].domain_id == "d1"


async def test_delete(store: LocalRunStore) -> None:
    run = AgentRun(domain_id="d1", prompt="p")
    await store.save(run)
    assert await store.delete(run.id) is True
    assert await store.load(run.id) is None


async def test_delete_nonexistent_returns_false(store: LocalRunStore) -> None:
    assert await store.delete("ghost") is False
