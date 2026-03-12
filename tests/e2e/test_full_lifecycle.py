"""End-to-end test — the money test."""

from httpx import AsyncClient


async def test_health(client: AsyncClient):
    """GET /health should return ok."""
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


async def test_experiment_not_found(client: AsyncClient):
    """GET /experiments/{nonexistent} should return 404."""
    resp = await client.get("/experiments/nonexistent-id")
    assert resp.status_code == 404


async def test_create_knowledge_via_api(client: AsyncClient):
    """POST /knowledge creates a knowledge atom."""
    resp = await client.post(
        "/knowledge",
        json={
            "context": "image classification",
            "claim": "CNNs outperform MLPs on image data",
            "confidence": 0.9,
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["atom_id"]
    assert data["action"] == "created"

    resp = await client.get("/knowledge")
    assert any(a["id"] == data["atom_id"] for a in resp.json())


async def test_delete_knowledge_via_api(client: AsyncClient):
    """DELETE /knowledge/{id} removes the knowledge atom."""
    resp = await client.post(
        "/knowledge",
        json={"context": "test delete", "claim": "to be deleted"},
    )
    assert resp.status_code == 201
    atom_id = resp.json()["atom_id"]

    resp = await client.delete(f"/knowledge/{atom_id}")
    assert resp.status_code == 204

    resp = await client.get("/knowledge")
    assert all(a["id"] != atom_id for a in resp.json())


async def test_delete_knowledge_not_found(client: AsyncClient):
    """DELETE /knowledge/{nonexistent} should return 404."""
    resp = await client.delete("/knowledge/nonexistent")
    assert resp.status_code == 404


async def test_knowledge_endpoints(client: AsyncClient):
    """Knowledge endpoints should work (empty for PoC)."""
    resp = await client.get("/knowledge")
    assert resp.status_code == 200
    assert resp.json() == []

    resp = await client.get("/knowledge/relevant", params={"query": "test"})
    assert resp.status_code == 200
    assert resp.json() == []
