"""E2E: HTTP freeze endpoint enforces the verification gate."""

from __future__ import annotations

import pytest


@pytest.fixture
async def domain_id_with_task(client) -> str:
    """Create a domain + task via the API; return the domain id."""
    create = await client.post("/domains", json={"name": "gated"})
    assert create.status_code == 201
    domain_id = create.json()["id"]
    task = await client.post(
        f"/domains/{domain_id}/task",
        json={"type": "regression", "config": {"data_path": "x.csv", "target_column": "y"}},
    )
    assert task.status_code == 201
    return domain_id


async def test_freeze_rejects_when_no_tools_verified(client, domain_id_with_task):
    resp = await client.post(f"/domains/{domain_id_with_task}/task/freeze")
    assert resp.status_code == 422
    body = resp.json()["detail"]
    assert "errors" in body
    assert any("load_data" in e for e in body["errors"])


async def test_freeze_succeeds_with_skip_verification_query(client, domain_id_with_task):
    resp = await client.post(
        f"/domains/{domain_id_with_task}/task/freeze",
        params={"skip_verification": "true"},
    )
    assert resp.status_code == 200
    assert resp.json()["frozen"] is True


async def test_post_agent_run_requires_domain_id(client):
    resp = await client.post("/agent/run", json={"prompt": "x"})
    # Pydantic 422 — domain_id is required
    assert resp.status_code == 422


async def test_post_agent_run_returns_422_when_task_not_ready(client, domain_id_with_task):
    resp = await client.post("/agent/run", json={"prompt": "x", "domain_id": domain_id_with_task})
    assert resp.status_code == 422
    body = resp.json()["detail"]
    assert body["kind"] == "task_not_ready"
