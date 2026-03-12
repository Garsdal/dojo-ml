"""Unit tests for domain service and local domain store."""

from pathlib import Path

import pytest

from agentml.core.domain import Domain, DomainStatus, DomainTool, ToolType
from agentml.runtime.domain_service import DomainService
from agentml.runtime.lab import LabEnvironment
from agentml.storage.local import LocalDomainStore


@pytest.fixture
def domain_store(tmp_dir: Path):
    return LocalDomainStore(base_dir=tmp_dir / "domains")


# --- LocalDomainStore tests ---


async def test_domain_save_load(domain_store: LocalDomainStore):
    domain = Domain(name="ML Research", description="Classification tasks")
    await domain_store.save(domain)

    loaded = await domain_store.load(domain.id)
    assert loaded is not None
    assert loaded.name == "ML Research"
    assert loaded.description == "Classification tasks"
    assert loaded.status == DomainStatus.DRAFT


async def test_domain_list(domain_store: LocalDomainStore):
    await domain_store.save(Domain(name="D1"))
    await domain_store.save(Domain(name="D2"))

    domains = await domain_store.list()
    assert len(domains) == 2


async def test_domain_delete(domain_store: LocalDomainStore):
    domain = Domain(name="To Delete")
    await domain_store.save(domain)

    assert await domain_store.delete(domain.id) is True
    assert await domain_store.load(domain.id) is None
    assert await domain_store.delete(domain.id) is False


async def test_domain_update(domain_store: LocalDomainStore):
    domain = Domain(name="Original")
    await domain_store.save(domain)

    domain.name = "Updated"
    domain.status = DomainStatus.ACTIVE
    await domain_store.update(domain)

    loaded = await domain_store.load(domain.id)
    assert loaded is not None
    assert loaded.name == "Updated"
    assert loaded.status == DomainStatus.ACTIVE


async def test_domain_with_tools(domain_store: LocalDomainStore):
    tool = DomainTool(
        name="load_data",
        description="Load the dataset",
        type=ToolType.DATA_LOADER,
        example_usage="import pandas as pd\ndf = pd.read_csv('data.csv')",
        parameters={"type": "object", "properties": {}},
        created_by="human",
    )
    domain = Domain(name="With Tools", tools=[tool])
    await domain_store.save(domain)

    loaded = await domain_store.load(domain.id)
    assert loaded is not None
    assert len(loaded.tools) == 1
    assert loaded.tools[0].name == "load_data"
    assert loaded.tools[0].type == ToolType.DATA_LOADER


# --- DomainService tests ---


async def test_domain_service_create(lab: LabEnvironment):
    service = DomainService(lab)
    domain = Domain(name="Service Test")
    domain_id = await service.create(domain)
    assert domain_id == domain.id


async def test_domain_service_get(lab: LabEnvironment):
    service = DomainService(lab)
    domain = Domain(name="Get Test")
    await service.create(domain)

    loaded = await service.get(domain.id)
    assert loaded is not None
    assert loaded.name == "Get Test"


async def test_domain_service_list(lab: LabEnvironment):
    service = DomainService(lab)
    await service.create(Domain(name="D1"))
    await service.create(Domain(name="D2"))

    domains = await service.list()
    assert len(domains) == 2


async def test_domain_service_activate(lab: LabEnvironment):
    service = DomainService(lab)
    domain = Domain(name="Activate Test")
    await service.create(domain)

    activated = await service.activate(domain.id)
    assert activated.status == DomainStatus.ACTIVE


async def test_domain_service_add_tool(lab: LabEnvironment):
    service = DomainService(lab)
    domain = Domain(name="Tool Test")
    await service.create(domain)

    tool = DomainTool(name="eval", description="Evaluate model")
    await service.add_tool(domain.id, tool)

    loaded = await service.get(domain.id)
    assert loaded is not None
    assert len(loaded.tools) == 1
    assert loaded.tools[0].name == "eval"


async def test_domain_service_remove_tool(lab: LabEnvironment):
    service = DomainService(lab)
    tool = DomainTool(name="to_remove")
    domain = Domain(name="Remove Tool Test", tools=[tool])
    await service.create(domain)

    await service.remove_tool(domain.id, tool.id)

    loaded = await service.get(domain.id)
    assert loaded is not None
    assert len(loaded.tools) == 0
