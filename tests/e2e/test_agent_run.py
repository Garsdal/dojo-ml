"""E2E tests for agent run API routes using the stub backend."""

import pytest


@pytest.fixture
def agent_settings(settings):
    """Override settings to use stub backend for E2E tests."""
    settings.agent.backend = "stub"
    return settings


@pytest.fixture
async def agent_client(agent_settings):
    """Async HTTP client configured with stub agent backend."""
    from httpx import ASGITransport, AsyncClient

    from agentml.api.app import create_app

    app = create_app(agent_settings)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


class TestAgentRunEndpoints:
    """E2E tests for agent run lifecycle."""

    async def test_start_run(self, agent_client):
        resp = await agent_client.post(
            "/agent/run",
            json={"prompt": "Test ML research task"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "running"
        assert data["prompt"] == "Test ML research task"
        assert data["id"]
        assert data["task_id"]

    async def test_list_runs(self, agent_client):
        # Start a run first
        await agent_client.post(
            "/agent/run",
            json={"prompt": "Test task"},
        )
        resp = await agent_client.get("/agent/runs")
        assert resp.status_code == 200
        runs = resp.json()
        assert len(runs) >= 1

    async def test_get_run(self, agent_client):
        # Start a run
        start_resp = await agent_client.post(
            "/agent/run",
            json={"prompt": "Test task"},
        )
        run_id = start_resp.json()["id"]

        resp = await agent_client.get(f"/agent/runs/{run_id}")
        assert resp.status_code == 200
        assert resp.json()["id"] == run_id

    async def test_get_nonexistent_run(self, agent_client):
        resp = await agent_client.get("/agent/runs/nonexistent")
        assert resp.status_code == 404

    async def test_stop_run(self, agent_client):
        start_resp = await agent_client.post(
            "/agent/run",
            json={"prompt": "Test task"},
        )
        run_id = start_resp.json()["id"]

        resp = await agent_client.post(f"/agent/runs/{run_id}/stop")
        assert resp.status_code == 200
        assert resp.json()["status"] == "stopped"

    async def test_stop_nonexistent_run(self, agent_client):
        resp = await agent_client.post("/agent/runs/nonexistent/stop")
        assert resp.status_code == 404

    async def test_start_run_with_tool_hints(self, agent_client):
        resp = await agent_client.post(
            "/agent/run",
            json={
                "prompt": "Test with hints",
                "tool_hints": [
                    {
                        "name": "fetch_dataset",
                        "description": "Load housing data",
                        "source": "https://example.com/data",
                    }
                ],
            },
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "running"

    async def test_start_run_with_custom_params(self, agent_client):
        resp = await agent_client.post(
            "/agent/run",
            json={
                "prompt": "Custom params test",
                "max_turns": 10,
                "max_budget_usd": 1.0,
            },
        )
        assert resp.status_code == 200
