"""Tests for WorkspaceScanner."""

from pathlib import Path

import pytest

from dojo.runtime.workspace_scanner import WorkspaceScanner


@pytest.fixture
def tmp_workspace(tmp_path: Path) -> Path:
    """Create a temporary workspace with some files."""
    # Data files
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "train.csv").write_text("col1,col2\n1,2\n3,4\n")
    (tmp_path / "data" / "test.csv").write_text("col1,col2\n5,6\n")

    # Python module
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "__init__.py").write_text("")
    (tmp_path / "src" / "features.py").write_text(
        '"""Feature engineering."""\n\n'
        "def engineer_features(df):\n"
        '    """Engineer features from a DataFrame."""\n'
        "    return df\n\n"
        "def _private_func():\n"
        "    pass\n"
    )

    # pyproject.toml
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'myproject'\n")

    return tmp_path


def test_scanner_finds_csv_files(tmp_workspace: Path):
    """get_summary reports the two CSV files in the workspace."""
    scanner = WorkspaceScanner()
    summary = scanner.get_summary(str(tmp_workspace))
    assert len(summary["data_files"]) == 2


def test_scanner_detects_pyproject(tmp_workspace: Path):
    """get_summary detects pyproject.toml and absence of requirements.txt."""
    scanner = WorkspaceScanner()
    summary = scanner.get_summary(str(tmp_workspace))
    assert summary["has_pyproject"] is True
    assert summary["has_requirements"] is False


def test_scanner_suggests_data_loaders(tmp_workspace: Path):
    """scan produces at least one data_loader suggestion for the CSV files."""
    scanner = WorkspaceScanner()
    suggestions = scanner.scan(str(tmp_workspace))
    data_loader_names = {s.name for s in suggestions if s.tool_type == "data_loader"}
    assert "load_train" in data_loader_names or any("train" in n for n in data_loader_names)


def test_scanner_suggests_functions(tmp_workspace: Path):
    """scan surfaces the public function defined in src/features.py."""
    scanner = WorkspaceScanner()
    suggestions = scanner.scan(str(tmp_workspace))
    func_names = {s.name for s in suggestions}
    assert "engineer_features" in func_names


def test_scanner_ignores_private_functions(tmp_workspace: Path):
    """scan does not suggest any function whose name starts with an underscore."""
    scanner = WorkspaceScanner()
    suggestions = scanner.scan(str(tmp_workspace))
    private_names = {s.name for s in suggestions if s.name.startswith("_")}
    assert len(private_names) == 0


def test_scanner_empty_workspace(tmp_path: Path):
    """An empty directory produces no data_files and no suggestions."""
    scanner = WorkspaceScanner()
    summary = scanner.get_summary(str(tmp_path))
    assert summary["data_files"] == []
    assert summary["has_pyproject"] is False
    suggestions = scanner.scan(str(tmp_path))
    assert suggestions == []


def test_scanner_summary_includes_path(tmp_workspace: Path):
    """get_summary echoes back the workspace path."""
    scanner = WorkspaceScanner()
    summary = scanner.get_summary(str(tmp_workspace))
    assert summary["path"] == str(tmp_workspace)


def test_scanner_summary_detects_no_venv(tmp_workspace: Path):
    """has_venv is False when neither .venv nor venv directories exist."""
    scanner = WorkspaceScanner()
    summary = scanner.get_summary(str(tmp_workspace))
    assert summary["has_venv"] is False


def test_scanner_summary_detects_venv(tmp_path: Path):
    """has_venv is True when a .venv directory is present."""
    (tmp_path / ".venv").mkdir()
    scanner = WorkspaceScanner()
    summary = scanner.get_summary(str(tmp_path))
    assert summary["has_venv"] is True


def test_scanner_detects_requirements(tmp_path: Path):
    """get_summary detects requirements.txt and absence of pyproject.toml."""
    (tmp_path / "requirements.txt").write_text("pandas\nscikit-learn\n")
    scanner = WorkspaceScanner()
    summary = scanner.get_summary(str(tmp_path))
    assert summary["has_requirements"] is True
    assert summary["has_pyproject"] is False


def test_scanner_data_loader_suggestion_has_code(tmp_workspace: Path):
    """Every data_loader suggestion carries non-empty code."""
    scanner = WorkspaceScanner()
    suggestions = scanner.scan(str(tmp_workspace))
    data_loaders = [s for s in suggestions if s.tool_type == "data_loader"]
    assert len(data_loaders) > 0
    for loader in data_loaders:
        assert loader.code != ""


def test_scanner_function_suggestion_tool_type(tmp_workspace: Path):
    """A non-evaluator function is suggested with tool_type='custom'."""
    scanner = WorkspaceScanner()
    suggestions = scanner.scan(str(tmp_workspace))
    func_suggestions = [s for s in suggestions if s.name == "engineer_features"]
    assert len(func_suggestions) >= 1
    assert all(s.tool_type == "custom" for s in func_suggestions)


def test_scanner_evaluator_function_tool_type(tmp_path: Path):
    """Functions with evaluator keywords get tool_type='evaluator'."""
    (tmp_path / "metrics.py").write_text(
        'def score_model(y_true, y_pred):\n    """Score a model."""\n    return 0.9\n'
    )
    scanner = WorkspaceScanner()
    suggestions = scanner.scan(str(tmp_path))
    evaluators = [s for s in suggestions if s.tool_type == "evaluator"]
    assert len(evaluators) >= 1
    assert any(s.name == "score_model" for s in evaluators)


def test_scanner_ignores_venv_data_files(tmp_path: Path):
    """Data files inside .venv are excluded from get_summary results."""
    venv = tmp_path / ".venv"
    venv.mkdir()
    (venv / "data.csv").write_text("col\n1\n")
    scanner = WorkspaceScanner()
    summary = scanner.get_summary(str(tmp_path))
    assert summary["data_files"] == []


def test_scanner_parquet_file(tmp_path: Path):
    """Parquet files are recognised as data files in get_summary."""
    (tmp_path / "train.parquet").write_bytes(b"PAR1")  # minimal magic bytes
    scanner = WorkspaceScanner()
    summary = scanner.get_summary(str(tmp_path))
    assert len(summary["data_files"]) == 1
    assert "train.parquet" in summary["data_files"][0]
