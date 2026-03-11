"""E2E tests for domain API routes."""

from httpx import AsyncClient


async def test_domain_crud(client: AsyncClient):
    """Full CRUD lifecycle for domains."""
    # Create
    resp = await client.post(
        "/domains",
        json={
            "name": "Housing Price Research",
            "description": "Predicting California housing prices",
            "prompt": "Focus on tree-based models and feature engineering",
        },
    )
    assert resp.status_code == 201
    domain = resp.json()
    domain_id = domain["id"]
    assert domain["name"] == "Housing Price Research"
    assert domain["status"] == "active"

    # Get
    resp = await client.get(f"/domains/{domain_id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == domain_id

    # List
    resp = await client.get("/domains")
    assert resp.status_code == 200
    assert len(resp.json()) >= 1

    # Update
    resp = await client.put(
        f"/domains/{domain_id}",
        json={"name": "Updated Name", "status": "paused"},
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "Updated Name"
    assert resp.json()["status"] == "paused"

    # Delete
    resp = await client.delete(f"/domains/{domain_id}")
    assert resp.status_code == 204


async def test_domain_not_found(client: AsyncClient):
    resp = await client.get("/domains/nonexistent")
    assert resp.status_code == 404


async def test_domain_tools(client: AsyncClient):
    """Domain tool management."""
    # Create domain
    resp = await client.post(
        "/domains",
        json={"name": "Tool Test Domain"},
    )
    domain_id = resp.json()["id"]

    # Add tool
    resp = await client.post(
        f"/domains/{domain_id}/tools",
        json={
            "name": "load_data",
            "description": "Load the training dataset",
            "type": "data_loader",
            "code": "def main(args): return {'rows': 100}",
        },
    )
    assert resp.status_code == 201
    tool = resp.json()
    assert tool["name"] == "load_data"
    tool_id = tool["id"]

    # List tools
    resp = await client.get(f"/domains/{domain_id}/tools")
    assert resp.status_code == 200
    assert len(resp.json()) == 1

    # Remove tool
    resp = await client.delete(f"/domains/{domain_id}/tools/{tool_id}")
    assert resp.status_code == 204


async def test_domain_experiments(client: AsyncClient):
    """Domain experiments endpoint."""
    # Create domain
    resp = await client.post(
        "/domains",
        json={"name": "Experiment Domain"},
    )
    domain_id = resp.json()["id"]

    # No experiments yet
    resp = await client.get(f"/domains/{domain_id}/experiments")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_domain_metrics_evolution(client: AsyncClient):
    """Domain metrics evolution endpoint."""
    resp = await client.post(
        "/domains",
        json={"name": "Metrics Domain"},
    )
    domain_id = resp.json()["id"]

    resp = await client.get(f"/domains/{domain_id}/metrics")
    assert resp.status_code == 200
    assert resp.json()["domain_id"] == domain_id
    assert resp.json()["metrics_evolution"] == []


async def test_domain_knowledge(client: AsyncClient):
    """Domain knowledge endpoints."""
    resp = await client.post(
        "/domains",
        json={"name": "Knowledge Domain"},
    )
    domain_id = resp.json()["id"]

    resp = await client.get(f"/domains/{domain_id}/knowledge")
    assert resp.status_code == 200
    assert resp.json() == []

    resp = await client.get(f"/domains/{domain_id}/knowledge/evolution")
    assert resp.status_code == 200
    assert resp.json()["snapshots"] == []


async def test_knowledge_with_domain_filter(client: AsyncClient):
    """Knowledge endpoints support domain_id filtering."""
    resp = await client.get("/knowledge", params={"domain_id": "nonexistent"})
    assert resp.status_code == 200
    assert resp.json() == []


async def test_knowledge_detail_endpoint(client: AsyncClient):
    """GET /knowledge/{id} returns atom with links and history."""
    # Create a knowledge atom first
    resp = await client.post(
        "/knowledge",
        json={
            "context": "Test experiment for detail endpoint",
            "claim": "Detail endpoint works correctly for knowledge atom retrieval",
        },
    )
    assert resp.status_code == 201
    atom_id = resp.json()["atom_id"]

    # Get detailed view
    resp = await client.get(f"/knowledge/{atom_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["atom"]["id"] == atom_id
    assert "links" in data
    assert "history" in data


async def test_knowledge_history_endpoint(client: AsyncClient):
    """GET /knowledge/{id}/history returns version history."""
    resp = await client.post(
        "/knowledge",
        json={
            "context": "History test from transformer experiments",
            "claim": "Version history endpoint works for tracking knowledge atom evolution",
        },
    )
    atom_id = resp.json()["atom_id"]

    resp = await client.get(f"/knowledge/{atom_id}/history")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
    assert len(resp.json()) >= 1
