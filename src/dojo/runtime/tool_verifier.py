"""ToolVerifier — runs a generated tool against its ToolContract.

The verifier exists to make the anti-cheating contract real: a Task can only be
frozen when every required tool runs successfully and produces output that
matches the contract's `returns_schema`.

Design:
- One tool at a time (`verify(tool, contract, workspace, fixtures=None)`).
- Stateless — the only side effect is running the sandbox.
- Caller controls execution order and threads outputs from earlier tools into
  later tools via `fixtures` (e.g. `evaluate` needs `y_pred`, which is derived
  from `load_data`'s output).

Returns a `VerificationResult` populated on the tool itself.
"""

from __future__ import annotations

import json
import textwrap
import time
from datetime import UTC, datetime
from typing import Any

from dojo.core.domain import DomainTool, VerificationResult, Workspace
from dojo.core.task import TASK_TYPE_REGISTRY, Task, TaskType, ToolContract
from dojo.interfaces.sandbox import Sandbox
from dojo.utils.logging import get_logger

logger = get_logger(__name__)


class ToolVerifier:
    """Runs a generated tool in the sandbox and validates its output shape."""

    def __init__(self, sandbox: Sandbox, *, timeout: float = 60.0) -> None:
        self.sandbox = sandbox
        self.timeout = timeout

    async def verify(
        self,
        tool: DomainTool,
        contract: ToolContract,
        workspace: Workspace | None,
        *,
        fixtures: dict[str, Any] | None = None,
        raw_output: dict[str, Any] | None = None,
    ) -> VerificationResult:
        """Verify a single tool against its contract.

        Args:
            tool: The generated tool (must have `code`).
            contract: The contract from `TASK_TYPE_REGISTRY[type].required_tools`.
            workspace: The domain's workspace (for cwd / python_path).
            fixtures: Sample parameter values to inject as locals when running
                the tool. Required for tools whose `params_schema` is non-empty.
            raw_output: If provided, populated in-place with the parsed JSON
                output from the tool. Used by `verify_required_tools` to thread
                outputs from one tool into the next (e.g. y_test → y_pred).

        Returns:
            A `VerificationResult` summarising the outcome. Always returns —
            never raises (errors land in `result.errors`).
        """
        errors: list[str] = []

        if not tool.code or not tool.code.strip():
            errors.append("tool has no code")
            return VerificationResult(verified=False, errors=errors)

        params = self._build_params(contract, fixtures, errors)
        if errors:
            return VerificationResult(verified=False, errors=errors)

        script = _wrap_for_execution(tool.code, params)

        cwd, python_path, env_vars = _workspace_args(workspace)

        start = time.monotonic()
        result = await self.sandbox.execute(
            script,
            cwd=cwd,
            python_path=python_path,
            env_vars=env_vars,
            timeout=self.timeout,
        )
        duration_ms = (time.monotonic() - start) * 1000.0

        if result.exit_code != 0:
            errors.append(
                f"tool exited with code {result.exit_code}: {(result.stderr or '').strip()[:500]}"
            )
            return VerificationResult(
                verified=False,
                errors=errors,
                duration_ms=duration_ms,
                verified_at=datetime.now(UTC),
            )

        stdout = (result.stdout or "").strip()
        if not stdout:
            errors.append("tool produced no stdout — must print JSON to stdout")
            return VerificationResult(
                verified=False,
                errors=errors,
                duration_ms=duration_ms,
                verified_at=datetime.now(UTC),
            )

        sample = self._parse_stdout(stdout, errors)
        if errors:
            return VerificationResult(
                verified=False,
                errors=errors,
                duration_ms=duration_ms,
                verified_at=datetime.now(UTC),
            )

        if raw_output is not None:
            raw_output.clear()
            raw_output.update(sample)

        self._validate_returns(sample, contract, errors)

        verified = not errors
        # Trim sample_output so we don't persist megabytes of training data
        return VerificationResult(
            verified=verified,
            errors=errors,
            sample_output=_summarise_output(sample),
            duration_ms=duration_ms,
            verified_at=datetime.now(UTC),
        )

    @staticmethod
    def _build_params(
        contract: ToolContract,
        fixtures: dict[str, Any] | None,
        errors: list[str],
    ) -> dict[str, Any]:
        """Build the kwargs to inject as locals before running the tool."""
        params: dict[str, Any] = {}
        for name in contract.params_schema:
            if fixtures is not None and name in fixtures:
                params[name] = fixtures[name]
            else:
                errors.append(
                    f"missing fixture for parameter {name!r} "
                    f"(contract requires {list(contract.params_schema)})"
                )
        return params

    @staticmethod
    def _parse_stdout(stdout: str, errors: list[str]) -> dict[str, Any]:
        """Pull the last JSON object out of stdout. Returns {} on failure."""
        # Try whole stdout first
        try:
            data = json.loads(stdout)
        except json.JSONDecodeError:
            # Fall back to last non-empty line — generated tools sometimes
            # print debug then JSON
            for line in reversed(stdout.splitlines()):
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    break
                except json.JSONDecodeError:
                    continue
            else:
                errors.append("stdout was not valid JSON")
                return {}

        if not isinstance(data, dict):
            errors.append(f"expected JSON object, got {type(data).__name__}")
            return {}
        return data

    @staticmethod
    def _validate_returns(
        sample: dict[str, Any], contract: ToolContract, errors: list[str]
    ) -> None:
        """Validate keys + best-effort types against `returns_schema`."""
        for key, spec in contract.returns_schema.items():
            if key not in sample:
                errors.append(f"missing required key {key!r} in output")
                continue
            value = sample[key]
            problem = _check_type(value, spec)
            if problem:
                errors.append(f"key {key!r}: {problem}")


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


async def verify_required_tools(
    tools: list[DomainTool],
    task: Task,
    *,
    sandbox: Sandbox,
    workspace: Workspace | None,
    timeout: float = 60.0,
) -> list[DomainTool]:
    """Verify each required tool for `task` in dependency order.

    Mutates `tools` in place: every tool whose name matches a contract gets
    its `verification` field populated. Tools the AI emitted that aren't part
    of the contract are left untouched.

    Returns the same list (for fluent use).
    """
    spec = TASK_TYPE_REGISTRY.get(task.type)
    if spec is None:
        return tools

    by_name = {t.name: t for t in tools}
    verifier = ToolVerifier(sandbox, timeout=timeout)
    raw_outputs: dict[str, dict[str, Any]] = {}

    for contract in spec.required_tools:
        tool = by_name.get(contract.name)
        if tool is None:
            continue
        fixtures = _build_fixtures(task.type, contract.name, raw_outputs)
        raw: dict[str, Any] = {}
        result = await verifier.verify(tool, contract, workspace, fixtures=fixtures, raw_output=raw)
        tool.verification = result
        if raw:
            raw_outputs[contract.name] = raw

    return tools


def _build_fixtures(
    task_type: TaskType,
    tool_name: str,
    raw_outputs: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    """Pick fixtures for a tool based on previously-verified tools' outputs.

    Regression: `evaluate` needs `y_pred`. We use `y_test` from `load_data` as
    a perfect-prediction fixture — if the contract is right and the tool's
    code is right, the output should still match the returns_schema.
    """
    if task_type == TaskType.REGRESSION and tool_name == "evaluate":
        load = raw_outputs.get("load_data")
        if load and isinstance(load.get("y_test"), list):
            return {"y_pred": load["y_test"]}
    return None


def _wrap_for_execution(code: str, params: dict[str, Any]) -> str:
    """Wrap tool code so injected params become local variables.

    Mirrors the pattern in `tools/domain_tools.py::_build_tool_script` so the
    verifier's execution environment matches the runtime MCP-handler one.
    """
    args_json = json.dumps(params)
    return textwrap.dedent(f"""\
        import json as _json

        _args = _json.loads({args_json!r})
        for _k, _v in _args.items():
            locals()[_k] = _v

        # Tool code begins
        {textwrap.indent(code, "        ").strip()}
    """)


def _workspace_args(
    workspace: Workspace | None,
) -> tuple[str | None, str | None, dict[str, str] | None]:
    if workspace is None or not workspace.ready:
        return None, None, None
    return (
        workspace.path or None,
        workspace.python_path,
        workspace.env_vars or None,
    )


def _check_type(value: Any, spec: str) -> str | None:
    """Best-effort type check — returns an error string or None.

    The schema is a free-form description like "list of float" or "float".
    We do loose, forgiving checks: presence + obvious mismatches.
    """
    s = spec.lower()
    if "list" in s:
        if not isinstance(value, list):
            return f"expected list, got {type(value).__name__}"
        if "list of list" in s and value and not isinstance(value[0], list):
            return "expected list of lists"
        return None
    if "float" in s or "number" in s:
        if not isinstance(value, (int, float)):
            return f"expected number, got {type(value).__name__}"
        return None
    if "int" in s:
        if not isinstance(value, int) or isinstance(value, bool):
            return f"expected int, got {type(value).__name__}"
        return None
    if "str" in s:
        if not isinstance(value, str):
            return f"expected str, got {type(value).__name__}"
        return None
    return None


def _summarise_output(sample: dict[str, Any], *, max_list_items: int = 3) -> dict[str, Any]:
    """Return a small, persistable summary of the tool output.

    Lists are truncated; nested lists keep their shape but only a few elements.
    Avoids persisting full training datasets in the JSON store.
    """
    out: dict[str, Any] = {}
    for k, v in sample.items():
        if isinstance(v, list):
            out[k] = {
                "type": "list",
                "length": len(v),
                "head": _summarise_list(v, max_list_items),
            }
        elif isinstance(v, dict):
            out[k] = {"type": "dict", "keys": list(v.keys())[:10]}
        else:
            out[k] = v
    return out


def _summarise_list(values: list[Any], n: int) -> list[Any]:
    head = values[:n]
    return [_summarise_list(item, n) if isinstance(item, list) else item for item in head]
