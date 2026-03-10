"""End-to-end test — the money test."""

import pytest
from httpx import ASGITransport, AsyncClient

from agentml.api.app import create_app
from agentml.config.settings import (
    AgentSettings,
    MemorySettings,
    Settings,
    StorageSettings,
    TrackingSettings,
)


async def test_health(client: AsyncClient):
    """GET /health should return ok."""
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


async def test_submit_task_and_get_results(client: AsyncClient):
    """POST /tasks with a prompt → GET /tasks/{id} → verify experiments + result."""
    # 1. POST /tasks
    resp = await client.post("/tasks", json={"prompt": "Compare models on iris"})
    assert resp.status_code == 200
    data = resp.json()
    task_id = data["id"]

    assert data["status"] == "completed"
    assert data["summary"] is not None
    assert len(data["experiments"]) >= 1
    assert data["experiments"][0]["metrics"] is not None
    assert data["metrics"]["accuracy"] == pytest.approx(0.95)

    # 2. GET /tasks/{id}
    resp = await client.get(f"/tasks/{task_id}")
    assert resp.status_code == 200
    task = resp.json()
    assert task["status"] == "completed"
    assert task["id"] == task_id
    assert len(task["experiments"]) >= 1

    # 3. GET /tasks (list)
    resp = await client.get("/tasks")
    assert resp.status_code == 200
    tasks = resp.json()
    assert len(tasks) >= 1

    # 4. GET /experiments
    resp = await client.get("/experiments")
    assert resp.status_code == 200
    experiments = resp.json()
    assert len(experiments) >= 1

    exp_id = experiments[0]["id"]

    # 5. GET /experiments/{id}
    resp = await client.get(f"/experiments/{exp_id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == exp_id

    # 6. GET /health
    resp = await client.get("/health")
    assert resp.json()["status"] == "ok"

    # 7. Knowledge was created by the stub agent (via tools pipeline)
    resp = await client.get("/knowledge")
    assert resp.status_code == 200
    atoms = resp.json()
    assert len(atoms) >= 1

    # 8. Knowledge search
    resp = await client.get("/knowledge/relevant", params={"query": "iris"})
    assert resp.status_code == 200

    # 9. Tracked metrics endpoint
    resp = await client.get(f"/tracking/{exp_id}/metrics")
    assert resp.status_code == 200
    assert "accuracy" in resp.json()


async def test_task_not_found(client: AsyncClient):
    """GET /tasks/{nonexistent} should return 404."""
    resp = await client.get("/tasks/nonexistent-id")
    assert resp.status_code == 404


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
    atom = resp.json()
    assert atom["claim"] == "CNNs outperform MLPs on image data"

    resp = await client.get("/knowledge")
    assert any(a["id"] == atom["id"] for a in resp.json())


async def test_delete_knowledge_via_api(client: AsyncClient):
    """DELETE /knowledge/{id} removes the knowledge atom."""
    # Create one
    resp = await client.post(
        "/knowledge",
        json={"context": "test", "claim": "to be deleted"},
    )
    assert resp.status_code == 201
    atom_id = resp.json()["id"]

    # Delete it
    resp = await client.delete(f"/knowledge/{atom_id}")
    assert resp.status_code == 204

    # Verify gone
    resp = await client.get("/knowledge")
    assert all(a["id"] != atom_id for a in resp.json())


async def test_delete_knowledge_not_found(client: AsyncClient):
    """DELETE /knowledge/{nonexistent} should return 404."""
    resp = await client.delete("/knowledge/nonexistent")
    assert resp.status_code == 404


async def test_full_lifecycle_with_mlflow(tmp_path):
    """Same lifecycle but with MLflow tracker."""
    settings = Settings(
        storage=StorageSettings(base_dir=tmp_path / ".agentml"),
        tracking=TrackingSettings(
            backend="mlflow",
            enabled=True,
            mlflow_tracking_uri=f"file:{tmp_path / 'mlruns'}",
            mlflow_experiment_name="e2e-test",
        ),
        memory=MemorySettings(backend="local"),
        agent=AgentSettings(backend="stub"),
    )
    app = create_app(settings)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post("/tasks", json={"prompt": "MLflow e2e"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "completed"

        # Verify metrics via tracking endpoint
        exp_id = data["experiments"][0]["id"]
        resp = await c.get(f"/tracking/{exp_id}/metrics")
        assert resp.status_code == 200
        assert resp.json()["accuracy"] == pytest.approx(0.95)


async def test_knowledge_endpoints(client: AsyncClient):
    """Knowledge endpoints should work (empty for PoC)."""
    resp = await client.get("/knowledge")
    assert resp.status_code == 200
    assert resp.json() == []

    resp = await client.get("/knowledge/relevant", params={"query": "test"})
    assert resp.status_code == 200
    assert resp.json() == []
