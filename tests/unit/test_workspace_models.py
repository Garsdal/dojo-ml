"""Tests for Workspace and CodeRun models."""

from dojo.core.domain import Domain, DomainTool, Workspace, WorkspaceSource
from dojo.core.experiment import CodeRun, ExperimentResult


def test_workspace_defaults():
    ws = Workspace()
    assert ws.source == WorkspaceSource.LOCAL
    assert ws.ready is False
    assert ws.python_path is None
    assert ws.env_vars == {}


def test_workspace_local_source():
    ws = Workspace(source=WorkspaceSource.LOCAL, path="/my/project")
    assert ws.path == "/my/project"
    assert ws.source == WorkspaceSource.LOCAL


def test_workspace_git_source():
    ws = Workspace(
        source=WorkspaceSource.GIT,
        git_url="https://github.com/user/repo.git",
        git_ref="main",
    )
    assert ws.git_url == "https://github.com/user/repo.git"
    assert ws.git_ref == "main"


def test_domain_with_workspace():
    ws = Workspace(source=WorkspaceSource.LOCAL, path="/my/project")
    domain = Domain(name="Test", workspace=ws)
    assert domain.workspace is not None
    assert domain.workspace.path == "/my/project"


def test_domain_without_workspace():
    domain = Domain(name="Test")
    assert domain.workspace is None


def test_code_run_defaults():
    cr = CodeRun()
    assert cr.run_number == 0
    assert cr.exit_code == 0
    assert cr.code_path == ""


def test_code_run_in_experiment_result():
    cr = CodeRun(run_number=1, code_path="experiments/abc/run_1.py", exit_code=0)
    result = ExperimentResult(metrics={"rmse": 1.5}, code_runs=[cr])
    assert len(result.code_runs) == 1
    assert result.code_runs[0].run_number == 1


def test_domain_tool_module_fields():
    """Phase 4: tools carry module_filename + entrypoint for the framework
    to import them at runtime."""
    tool = DomainTool(
        name="load_data",
        description="Load training data",
        code="def load_data():\n    return [], [], [], []\n",
        module_filename="load_data.py",
        entrypoint="load_data",
        return_description="4-tuple of train/test arrays",
    )
    assert tool.code != ""
    assert tool.module_filename == "load_data.py"
    assert tool.entrypoint == "load_data"
    assert tool.return_description == "4-tuple of train/test arrays"


def test_domain_tool_module_field_defaults():
    """A bare DomainTool has empty module_filename / entrypoint / code."""
    tool = DomainTool(name="hint_tool", description="A hint")
    assert tool.module_filename == ""
    assert tool.entrypoint == ""
    assert tool.code == ""
    assert tool.return_description == ""


def test_workspace_empty_source():
    ws = Workspace(source=WorkspaceSource.EMPTY)
    assert ws.source == WorkspaceSource.EMPTY
    assert ws.path == ""
    assert ws.git_url is None


def test_workspace_env_vars():
    ws = Workspace(env_vars={"FOO": "bar", "BAZ": "qux"})
    assert ws.env_vars["FOO"] == "bar"
    assert ws.env_vars["BAZ"] == "qux"


def test_workspace_python_path():
    ws = Workspace(python_path="/my/project/.venv/bin/python")
    assert ws.python_path == "/my/project/.venv/bin/python"


def test_workspace_ready_flag():
    ws_not_ready = Workspace(path="/proj", ready=False)
    ws_ready = Workspace(path="/proj", ready=True)
    assert ws_not_ready.ready is False
    assert ws_ready.ready is True


def test_code_run_with_description():
    cr = CodeRun(run_number=2, description="Train baseline model", exit_code=0)
    assert cr.description == "Train baseline model"
    assert cr.run_number == 2


def test_code_run_failed_exit_code():
    cr = CodeRun(run_number=1, exit_code=1)
    assert cr.exit_code == 1


def test_experiment_result_code_runs_default():
    result = ExperimentResult()
    assert result.code_runs == []


def test_experiment_result_multiple_code_runs():
    runs = [
        CodeRun(run_number=1, code_path="experiments/x/run_1.py", exit_code=0),
        CodeRun(run_number=2, code_path="experiments/x/run_2.py", exit_code=0),
    ]
    result = ExperimentResult(metrics={"rmse": 1.2}, code_runs=runs)
    assert len(result.code_runs) == 2
    assert result.code_runs[1].run_number == 2
