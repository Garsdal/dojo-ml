"""Tests for workspace persistence in LocalDomainStore."""

from pathlib import Path

from dojo.core.domain import Domain, DomainTool, Workspace, WorkspaceSource
from dojo.storage.local import LocalDomainStore


async def test_domain_with_workspace_roundtrip(tmp_path: Path):
    """Workspace is persisted and loaded correctly."""
    store = LocalDomainStore(tmp_path / "domains")

    ws = Workspace(
        source=WorkspaceSource.LOCAL,
        path="/my/project",
        python_path="/my/project/.venv/bin/python",
        ready=True,
        env_vars={"MY_VAR": "value"},
    )
    domain = Domain(name="Test", workspace=ws)
    await store.save(domain)

    loaded = await store.load(domain.id)
    assert loaded is not None
    assert loaded.workspace is not None
    assert loaded.workspace.path == "/my/project"
    assert loaded.workspace.python_path == "/my/project/.venv/bin/python"
    assert loaded.workspace.ready is True
    assert loaded.workspace.env_vars == {"MY_VAR": "value"}
    assert loaded.workspace.source == WorkspaceSource.LOCAL


async def test_domain_without_workspace_roundtrip(tmp_path: Path):
    """Domain without workspace persists and loads with workspace=None."""
    store = LocalDomainStore(tmp_path / "domains")
    domain = Domain(name="NoWorkspace")
    await store.save(domain)

    loaded = await store.load(domain.id)
    assert loaded is not None
    assert loaded.workspace is None


async def test_domain_tool_module_roundtrip(tmp_path: Path):
    """Phase 4: tools persist with module_filename + entrypoint on the task."""
    from dojo.core.task import Task

    store = LocalDomainStore(tmp_path / "domains")

    tool = DomainTool(
        name="my_tool",
        code="def my_tool():\n    return 1\n",
        module_filename="my_tool.py",
        entrypoint="my_tool",
        return_description="Returns 1",
    )
    domain = Domain(name="Test", task=Task(tools=[tool]))
    await store.save(domain)

    loaded = await store.load(domain.id)
    assert loaded is not None
    assert loaded.task is not None
    loaded_tool = loaded.task.tools[0]
    assert loaded_tool.module_filename == "my_tool.py"
    assert loaded_tool.entrypoint == "my_tool"
    assert loaded_tool.code.startswith("def my_tool")
    assert loaded_tool.return_description == "Returns 1"


async def test_domain_git_workspace_roundtrip(tmp_path: Path):
    """Git workspace fields persist correctly."""
    store = LocalDomainStore(tmp_path / "domains")

    ws = Workspace(
        source=WorkspaceSource.GIT,
        git_url="https://github.com/user/repo.git",
        git_ref="main",
    )
    domain = Domain(name="GitTest", workspace=ws)
    await store.save(domain)

    loaded = await store.load(domain.id)
    assert loaded.workspace.source == WorkspaceSource.GIT
    assert loaded.workspace.git_url == "https://github.com/user/repo.git"
    assert loaded.workspace.git_ref == "main"


async def test_workspace_ready_false_persists(tmp_path: Path):
    """Workspace with ready=False is persisted and loaded with ready=False."""
    store = LocalDomainStore(tmp_path / "domains")

    ws = Workspace(source=WorkspaceSource.LOCAL, path="/proj", ready=False)
    domain = Domain(name="NotReady", workspace=ws)
    await store.save(domain)

    loaded = await store.load(domain.id)
    assert loaded.workspace is not None
    assert loaded.workspace.ready is False


async def test_workspace_env_vars_roundtrip(tmp_path: Path):
    """Multiple env vars are persisted and loaded correctly."""
    store = LocalDomainStore(tmp_path / "domains")

    ws = Workspace(
        source=WorkspaceSource.LOCAL,
        path="/proj",
        env_vars={"FOO": "bar", "BAZ": "qux", "SECRET_KEY": "12345"},
    )
    domain = Domain(name="EnvTest", workspace=ws)
    await store.save(domain)

    loaded = await store.load(domain.id)
    assert loaded.workspace.env_vars == {"FOO": "bar", "BAZ": "qux", "SECRET_KEY": "12345"}


async def test_workspace_empty_env_vars_roundtrip(tmp_path: Path):
    """Empty env_vars dict is preserved on roundtrip."""
    store = LocalDomainStore(tmp_path / "domains")

    ws = Workspace(source=WorkspaceSource.LOCAL, path="/proj", env_vars={})
    domain = Domain(name="EmptyEnv", workspace=ws)
    await store.save(domain)

    loaded = await store.load(domain.id)
    assert loaded.workspace.env_vars == {}


async def test_domain_tool_default_fields_roundtrip(tmp_path: Path):
    """A tool created with only a name should round-trip with empty defaults
    on the new fields (no module_filename, no entrypoint, no code)."""
    from dojo.core.task import Task

    store = LocalDomainStore(tmp_path / "domains")

    tool = DomainTool(
        name="hint_tool",
        description="A semantic hint",
        example_usage="import pandas as pd\ndf = pd.read_csv('data.csv')",
    )
    domain = Domain(name="HintDomain", task=Task(tools=[tool]))
    await store.save(domain)

    loaded = await store.load(domain.id)
    assert loaded is not None
    assert loaded.task is not None
    lt = loaded.task.tools[0]
    assert lt.module_filename == ""
    assert lt.entrypoint == ""
    assert lt.code == ""
    assert lt.example_usage == "import pandas as pd\ndf = pd.read_csv('data.csv')"


async def test_workspace_dependencies_file_roundtrip(tmp_path: Path):
    """dependencies_file field persists correctly."""
    store = LocalDomainStore(tmp_path / "domains")

    ws = Workspace(
        source=WorkspaceSource.LOCAL,
        path="/proj",
        dependencies_file="requirements.txt",
    )
    domain = Domain(name="DepFile", workspace=ws)
    await store.save(domain)

    loaded = await store.load(domain.id)
    assert loaded.workspace.dependencies_file == "requirements.txt"


async def test_workspace_setup_script_roundtrip(tmp_path: Path):
    """setup_script field persists correctly."""
    store = LocalDomainStore(tmp_path / "domains")

    ws = Workspace(
        source=WorkspaceSource.LOCAL,
        path="/proj",
        setup_script="bash setup.sh",
    )
    domain = Domain(name="SetupScript", workspace=ws)
    await store.save(domain)

    loaded = await store.load(domain.id)
    assert loaded.workspace.setup_script == "bash setup.sh"


async def test_domain_with_workspace_update(tmp_path: Path):
    """Updating a domain with a workspace persists the updated workspace."""
    store = LocalDomainStore(tmp_path / "domains")

    domain = Domain(
        name="UpdateTest",
        workspace=Workspace(source=WorkspaceSource.LOCAL, path="/old", ready=False),
    )
    await store.save(domain)

    # Update the workspace to ready=True with a new path
    domain.workspace = Workspace(source=WorkspaceSource.LOCAL, path="/new", ready=True)
    await store.update(domain)

    loaded = await store.load(domain.id)
    assert loaded.workspace.path == "/new"
    assert loaded.workspace.ready is True
