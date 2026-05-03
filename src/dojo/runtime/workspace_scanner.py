"""WorkspaceScanner — auto-detect project structure for tool suggestions."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar


@dataclass
class ToolSuggestion:
    """A suggested domain tool derived from workspace scanning."""

    name: str
    description: str
    tool_type: str
    code: str
    example_usage: str
    parameters: dict[str, Any]


class WorkspaceScanner:
    """Scans a workspace directory and suggests domain tools.

    Detects:
    - CSV/parquet/JSON data files → data_loader tools
    - Python functions in src/lib modules → custom tools
    - Evaluation functions (score*, evaluate*, metric*) → evaluator tools
    """

    DATA_EXTENSIONS: ClassVar[set[str]] = {".csv", ".parquet", ".json", ".jsonl", ".tsv"}
    MAX_DATA_FILES = 10
    MAX_MODULES = 5

    def scan(self, workspace_path: str) -> list[ToolSuggestion]:
        """Scan workspace and return tool suggestions."""
        path = Path(workspace_path)
        suggestions: list[ToolSuggestion] = []

        data_files = self._find_data_files(path)
        suggestions.extend(self._suggest_data_loaders(data_files, path))

        py_funcs = self._find_python_functions(path)
        suggestions.extend(self._suggest_from_functions(py_funcs))

        return suggestions

    def get_summary(self, workspace_path: str) -> dict[str, Any]:
        """Return a human-readable summary of the workspace."""
        path = Path(workspace_path)
        data_files = self._find_data_files(path)
        py_modules = list(self._find_python_modules(path))

        return {
            "path": str(path),
            "data_files": [str(f.relative_to(path)) for f in data_files],
            "python_modules": py_modules,
            "has_pyproject": (path / "pyproject.toml").exists(),
            "has_requirements": (path / "requirements.txt").exists(),
            "has_venv": (path / ".venv").exists() or (path / "venv").exists(),
        }

    # --- Private helpers ---

    def _find_data_files(self, root: Path) -> list[Path]:
        """Find data files in the workspace, excluding common non-data dirs."""
        exclude_dirs = {".venv", "venv", ".git", "__pycache__", "node_modules", ".tox"}
        files: list[Path] = []

        for f in root.rglob("*"):
            if (
                f.is_file()
                and f.suffix in self.DATA_EXTENSIONS
                and not any(p.name in exclude_dirs for p in f.parents)
            ):
                files.append(f)
                if len(files) >= self.MAX_DATA_FILES:
                    break

        return files

    def _find_python_modules(self, root: Path) -> list[str]:
        """Find importable Python module paths."""
        modules: list[str] = []
        for py_file in root.rglob("*.py"):
            if py_file.name.startswith("_"):
                continue
            try:
                rel = py_file.relative_to(root)
                module_path = str(rel).replace("/", ".").replace("\\", ".")[:-3]
                modules.append(module_path)
            except ValueError:
                pass
        return modules[: self.MAX_MODULES]

    def _find_python_functions(self, root: Path) -> list[dict[str, Any]]:
        """Find public functions in Python modules."""
        results: list[dict[str, Any]] = []
        src_dirs = ["src", "lib", ""]

        for src_dir in src_dirs:
            search_root = root / src_dir if src_dir else root
            if not search_root.exists():
                continue

            for py_file in search_root.rglob("*.py"):
                if py_file.name.startswith("_"):
                    continue
                try:
                    rel = py_file.relative_to(root)
                    module = str(rel)[:-3].replace("/", ".").replace("\\", ".")
                    funcs = self._extract_functions(py_file, module)
                    results.extend(funcs)
                except (ValueError, SyntaxError, OSError):
                    pass

        return results[:20]

    @staticmethod
    def _extract_functions(py_file: Path, module: str) -> list[dict[str, Any]]:
        """Extract function signatures from a Python file using AST."""
        try:
            tree = ast.parse(py_file.read_text())
        except SyntaxError:
            return []

        functions = []
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and not node.name.startswith("_"):
                docstring = ast.get_docstring(node) or ""
                params = [a.arg for a in node.args.args if a.arg != "self"]
                functions.append(
                    {
                        "name": node.name,
                        "module": module,
                        "docstring": docstring,
                        "params": params,
                    }
                )
        return functions

    def _suggest_data_loaders(self, data_files: list[Path], root: Path) -> list[ToolSuggestion]:
        """Generate data loader tool suggestions for CSV/parquet files."""
        suggestions = []
        for f in data_files:
            rel_path = f.relative_to(root)
            stem = f.stem.replace("-", "_").replace(" ", "_").lower()
            tool_name = f"load_{stem}"
            ext = f.suffix

            if ext == ".csv":
                code = f"import pandas as pd\nresult = pd.read_csv('{rel_path}').head(5).to_dict()\nprint(__import__('json').dumps(result))"
                desc = f"Load {rel_path} as a pandas DataFrame (returns first 5 rows as preview)"
            elif ext == ".parquet":
                code = f"import pandas as pd\nresult = pd.read_parquet('{rel_path}').head(5).to_dict()\nprint(__import__('json').dumps(result))"
                desc = f"Load {rel_path} as a pandas DataFrame (returns first 5 rows as preview)"
            else:
                code = f"import json\nwith open('{rel_path}') as f:\n    data = json.load(f)\nprint(json.dumps(data if isinstance(data, dict) else data[:5]))"
                desc = f"Load {rel_path} as JSON"

            suggestions.append(
                ToolSuggestion(
                    name=tool_name,
                    description=desc,
                    tool_type="data_loader",
                    code=code,
                    example_usage=f"# Call {tool_name}() to load the data",
                    parameters={},
                )
            )

        return suggestions

    def _suggest_from_functions(self, functions: list[dict[str, Any]]) -> list[ToolSuggestion]:
        """Generate tool suggestions from Python functions."""
        suggestions = []
        eval_keywords = {"score", "evaluate", "metric", "accuracy", "loss", "rmse", "mae"}

        for func in functions:
            name = func["name"]
            module = func["module"]
            params = func["params"]
            docstring = func["docstring"]

            # Determine tool type
            is_evaluator = any(kw in name.lower() for kw in eval_keywords)
            tool_type = "evaluator" if is_evaluator else "custom"

            call_str = f"{name}({', '.join(params)})" if params else f"{name}()"

            code = (
                f"from {module} import {name}\n"
                f"result = {call_str}\n"
                f"print(__import__('json').dumps(str(result)))"
            )

            example = f"from {module} import {name}\nresult = {name}({', '.join(f'{p}=...' for p in params)})"

            suggestions.append(
                ToolSuggestion(
                    name=name,
                    description=docstring or f"Call {module}.{name}",
                    tool_type=tool_type,
                    code=code,
                    example_usage=example,
                    parameters={
                        p: {"type": "string", "description": f"Parameter: {p}"} for p in params
                    },
                )
            )

        return suggestions
