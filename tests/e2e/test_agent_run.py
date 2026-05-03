"""E2E tests for agent run API routes using the stub backend."""

import pytest

from dojo.core.domain import Domain, DomainTool, ToolType, VerificationResult
from dojo.core.task import TaskType


@pytest.fixture
def agent_settings(settings):
    """Override settings to use stub backend for E2E tests."""
    settings.agent.backend = "stub"
    return settings


@pytest.fixture
async def agent_client(agent_settings):
    """Async HTTP client configured with stub agent backend."""
    from httpx import ASGITransport, AsyncClient

    from dojo.api.app import create_app

    app = create_app(agent_settings)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
async def ready_domain_id(agent_settings) -> str:
    """A domain with a frozen task and verified required tools.

    Built once per test via the same lab the app would build, then handed back
    so the test can POST `/agent/run` with `domain_id=ready_domain_id`.
    """
    from dojo.api.deps import build_lab
    from dojo.runtime.task_service import TaskService

    lab = build_lab(agent_settings)
    domain = Domain(name="e2e-ready")
    await lab.domain_store.save(domain)
    svc = TaskService(lab)
    await svc.create(domain.id, task_type=TaskType.REGRESSION)
    domain = await lab.domain_store.load(domain.id)
    domain.task.tools = [
        DomainTool(
            name="load_data",
            type=ToolType.DATA_LOADER,
            code="print('{}')",
            verification=VerificationResult(verified=True),
        ),
        DomainTool(
            name="evaluate",
            type=ToolType.EVALUATOR,
            code="print('{}')",
            verification=VerificationResult(verified=True),
        ),
    ]
    await lab.domain_store.save(domain)
    await svc.freeze(domain.id)
    return domain.id


class TestAgentRunEndpoints:
    """E2E tests for agent run lifecycle."""

    async def test_start_run(self, agent_client, ready_domain_id):
        resp = await agent_client.post(
            "/agent/run",
            json={"prompt": "Test ML research task", "domain_id": ready_domain_id},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "running"
        assert data["prompt"] == "Test ML research task"
        assert data["id"]
        assert data["domain_id"] == ready_domain_id

    async def test_list_runs(self, agent_client, ready_domain_id):
        await agent_client.post(
            "/agent/run",
            json={"prompt": "Test task", "domain_id": ready_domain_id},
        )
        resp = await agent_client.get("/agent/runs")
        assert resp.status_code == 200
        runs = resp.json()
        assert len(runs) >= 1

    async def test_get_run(self, agent_client, ready_domain_id):
        start_resp = await agent_client.post(
            "/agent/run",
            json={"prompt": "Test task", "domain_id": ready_domain_id},
        )
        run_id = start_resp.json()["id"]

        resp = await agent_client.get(f"/agent/runs/{run_id}")
        assert resp.status_code == 200
        assert resp.json()["id"] == run_id

    async def test_get_nonexistent_run(self, agent_client):
        resp = await agent_client.get("/agent/runs/nonexistent")
        assert resp.status_code == 404

    async def test_stop_run(self, agent_client, ready_domain_id):
        start_resp = await agent_client.post(
            "/agent/run",
            json={"prompt": "Test task", "domain_id": ready_domain_id},
        )
        run_id = start_resp.json()["id"]

        resp = await agent_client.post(f"/agent/runs/{run_id}/stop")
        assert resp.status_code == 200
        assert resp.json()["status"] == "stopped"

    async def test_stop_nonexistent_run(self, agent_client):
        resp = await agent_client.post("/agent/runs/nonexistent/stop")
        assert resp.status_code == 404

    async def test_start_run_with_tool_hints(self, agent_client, ready_domain_id):
        resp = await agent_client.post(
            "/agent/run",
            json={
                "prompt": "Test with hints",
                "domain_id": ready_domain_id,
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

    async def test_start_run_with_custom_params(self, agent_client, ready_domain_id):
        resp = await agent_client.post(
            "/agent/run",
            json={
                "prompt": "Custom params test",
                "domain_id": ready_domain_id,
                "max_turns": 10,
                "max_budget_usd": 1.0,
            },
        )
        assert resp.status_code == 200

    async def test_start_run_rejects_unknown_domain(self, agent_client):
        resp = await agent_client.post(
            "/agent/run",
            json={"prompt": "x", "domain_id": "ghost"},
        )
        assert resp.status_code == 422
        assert "task_not_ready" in str(resp.json())

    async def test_start_run_requires_domain_id(self, agent_client):
        resp = await agent_client.post("/agent/run", json={"prompt": "x"})
        assert resp.status_code == 422
