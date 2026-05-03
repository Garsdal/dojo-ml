"""ToolVerifier — runs a generated tool module against its ToolContract.

Phase 4: tools are Python modules with named entrypoints. The verifier writes
the modules to a tempdir, spawns a subprocess that imports the module and
calls the entrypoint with `**fixtures`, then validates the return value
against the contract.

Design:
- Import-based, not script-based. The subprocess uses ``importlib.util`` so the
  agent's eventual run-time experience matches the verifier's.
- Subprocess for isolation (so the dojo process doesn't leak imports / pollute
  ``sys.modules`` from sketchy generated code).
- Stateless. ``ToolVerifier.verify`` is one tool; ``verify_required_tools`` is
  the orchestrator that lays out the tempdir with all sibling modules so
  ``evaluate.py`` can ``from load_data import load_data``.

Returns a `VerificationResult` populated on the tool itself.
"""

from __future__ import annotations

import json
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from dojo.core.domain import DomainTool, VerificationResult, Workspace
from dojo.core.task import TASK_TYPE_REGISTRY, Task, TaskType, ToolContract
from dojo.interfaces.sandbox import Sandbox
from dojo.utils.logging import get_logger

logger = get_logger(__name__)

_RESULT_MARKER = "__DOJO_VERIFY_RESULT__:"
_ERROR_MARKER = "__DOJO_VERIFY_ERROR__:"


class ToolVerifier:
    """Imports a generated tool module in a subprocess and validates its return."""

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
        module_dir: Path | None = None,
    ) -> VerificationResult:
        """Verify a single tool against its contract.

        Args:
            tool: The generated tool (must have ``code`` and ``module_filename``
                / ``entrypoint``; falls back to contract defaults).
            contract: The contract from `TASK_TYPE_REGISTRY[type].required_tools`.
            workspace: The domain's workspace (for python_path / env_vars).
                ``cwd`` is overridden to ``module_dir`` so ``importlib`` resolves
                sibling modules deterministically.
            fixtures: Sample parameter values to pass as kwargs to the tool's
                entrypoint. Required for tools whose ``params_schema`` is non-empty.
            raw_output: If provided, populated in-place with the tool's return
                value (normalised to a dict). Used by `verify_required_tools` to
                thread outputs from one tool into the next (e.g. y_test → y_pred).
            module_dir: Directory containing the module file (and any siblings).
                When omitted, the verifier creates its own tempdir and writes
                the tool there.

        Returns:
            A `VerificationResult` summarising the outcome. Always returns —
            never raises (errors land in ``result.errors``).
        """
        errors: list[str] = []

        if not tool.code or not tool.code.strip():
            errors.append("tool has no code")
            return VerificationResult(verified=False, errors=errors)

        params = self._build_params(contract, fixtures, errors)
        if errors:
            return VerificationResult(verified=False, errors=errors)

        module_filename = tool.module_filename or contract.module_filename or f"{tool.name}.py"
        entrypoint = tool.entrypoint or contract.entrypoint or tool.name

        owns_dir = module_dir is None
        dir_path = module_dir or Path(tempfile.mkdtemp(prefix="dojo_verify_"))

        try:
            (dir_path / module_filename).write_text(tool.code)

            runner = _build_verifier_runner(
                module_filename=module_filename,
                entrypoint=entrypoint,
                fixtures=params,
            )

            _cwd, python_path, env_vars = _workspace_args(workspace)

            start = time.monotonic()
            result = await self.sandbox.execute(
                runner,
                cwd=str(dir_path),
                python_path=python_path,
                env_vars=env_vars,
                timeout=self.timeout,
                name=f"verify_{tool.name}",
            )
            duration_ms = (time.monotonic() - start) * 1000.0

            stdout = result.stdout or ""
            stderr = result.stderr or ""

            error_payload = _scan_marker(stdout, _ERROR_MARKER)
            if error_payload is not None:
                msg = (
                    error_payload.get("message")
                    or error_payload.get("type")
                    or "verifier subprocess raised"
                )
                errors.append(f"{tool.name} raised: {msg}")
                return VerificationResult(
                    verified=False,
                    errors=errors,
                    duration_ms=duration_ms,
                    verified_at=datetime.now(UTC),
                )

            result_payload = _scan_marker(stdout, _RESULT_MARKER)
            if result_payload is None:
                if result.exit_code != 0:
                    errors.append(
                        f"{tool.name} exited with code {result.exit_code}: "
                        f"{stderr.strip()[:500] or stdout.strip()[:500]}"
                    )
                else:
                    errors.append(
                        f"{tool.name} produced no result marker — "
                        f"the verifier looks for a line starting with {_RESULT_MARKER!r}. "
                        f"stdout tail: {stdout.strip()[-300:]!r}"
                    )
                return VerificationResult(
                    verified=False,
                    errors=errors,
                    duration_ms=duration_ms,
                    verified_at=datetime.now(UTC),
                )

            sample = _normalise_sample(result_payload, contract, errors)
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

            return VerificationResult(
                verified=not errors,
                errors=errors,
                sample_output=_summarise_output(sample),
                duration_ms=duration_ms,
                verified_at=datetime.now(UTC),
            )
        finally:
            if owns_dir:
                _rmtree_quiet(dir_path)

    @staticmethod
    def _build_params(
        contract: ToolContract,
        fixtures: dict[str, Any] | None,
        errors: list[str],
    ) -> dict[str, Any]:
        """Build the kwargs to pass to the tool's entrypoint."""
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

    Lays out a single tempdir with every required tool's module file, so that
    ``evaluate.py`` can ``from load_data import load_data`` during its own
    verification. Mutates ``tools`` in place: every tool whose name matches a
    contract gets its ``verification`` field populated.

    Returns the same list (for fluent use).
    """
    spec = TASK_TYPE_REGISTRY.get(task.type)
    if spec is None:
        return tools

    by_name = {t.name: t for t in tools}
    verifier = ToolVerifier(sandbox, timeout=timeout)
    raw_outputs: dict[str, dict[str, Any]] = {}

    with tempfile.TemporaryDirectory(prefix="dojo_verify_") as tmp:
        module_dir = Path(tmp)
        # Pre-write every tool with non-empty code so cross-imports resolve.
        for contract in spec.required_tools:
            tool = by_name.get(contract.name)
            if tool and tool.code:
                filename = tool.module_filename or contract.module_filename or f"{tool.name}.py"
                (module_dir / filename).write_text(tool.code)

        for contract in spec.required_tools:
            tool = by_name.get(contract.name)
            if tool is None:
                continue
            fixtures = _build_fixtures(task.type, contract.name, raw_outputs)
            raw: dict[str, Any] = {}
            result = await verifier.verify(
                tool,
                contract,
                workspace,
                fixtures=fixtures,
                raw_output=raw,
                module_dir=module_dir,
            )
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

    Regression: `evaluate(y_pred)` needs ``y_pred``. We use ``y_test`` from
    ``load_data`` as a perfect-prediction fixture — if the contract is right
    and the tool's code is right, evaluate's output should still match the
    returns_schema.
    """
    if task_type == TaskType.REGRESSION and tool_name == "evaluate":
        load = raw_outputs.get("load_data")
        if load and isinstance(load.get("y_test"), list):
            return {"y_pred": load["y_test"]}
    return None


def _build_verifier_runner(
    *,
    module_filename: str,
    entrypoint: str,
    fixtures: dict[str, Any],
) -> str:
    """Build the subprocess script that imports the module and calls entrypoint.

    The script normalises the return value (numpy → list, tuple → list) and
    prints exactly one marker line so the parent can parse it deterministically.
    """
    fixtures_repr = repr(fixtures)
    module_name = module_filename.removesuffix(".py")
    return f"""\
import importlib.util, json, sys, traceback
from pathlib import Path

_HERE = Path(__file__).parent
sys.path.insert(0, str(_HERE))


def _to_jsonable(value):
    # numpy arrays → list (without importing numpy unless needed)
    if hasattr(value, "tolist") and callable(value.tolist):
        try:
            return _to_jsonable(value.tolist())
        except Exception:
            pass
    if isinstance(value, (tuple, list)):
        return [_to_jsonable(v) for v in value]
    if isinstance(value, dict):
        return {{k: _to_jsonable(v) for k, v in value.items()}}
    if isinstance(value, (bool, int, float, str)) or value is None:
        return value
    return str(value)


try:
    spec = importlib.util.spec_from_file_location({module_name!r}, str(_HERE / {module_filename!r}))
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {{ {module_filename!r} }}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[{module_name!r}] = module
    spec.loader.exec_module(module)

    func = getattr(module, {entrypoint!r}, None)
    if func is None:
        raise AttributeError(
            f"module {{ {module_name!r} }} has no entrypoint {{ {entrypoint!r} }}"
        )
    if not callable(func):
        raise TypeError(f"{{ {entrypoint!r} }} on module is not callable")

    fixtures = {fixtures_repr}
    result = func(**fixtures)
    payload = _to_jsonable(result)
    print({_RESULT_MARKER!r} + json.dumps(payload))
except Exception as e:
    print({_ERROR_MARKER!r} + json.dumps({{
        "type": type(e).__name__,
        "message": str(e),
        "traceback": traceback.format_exc(),
    }}))
    sys.exit(1)
"""


def _scan_marker(stdout: str, marker: str) -> Any | None:
    """Find the last line that begins with ``marker`` and parse the JSON tail.

    Returns the parsed value, or None if no such line is present (or it didn't
    parse).
    """
    for line in reversed(stdout.splitlines()):
        line = line.rstrip()
        if not line.startswith(marker):
            continue
        try:
            return json.loads(line[len(marker) :])
        except json.JSONDecodeError:
            return None
    return None


def _normalise_sample(payload: Any, contract: ToolContract, errors: list[str]) -> dict[str, Any]:
    """Convert the tool's return value to a dict keyed by ``returns_schema``.

    For ``return_kind == "tuple"``: zip positional items with schema keys.
    For ``return_kind == "dict"``: ensure it's a dict; pass through.
    """
    if contract.return_kind == "tuple":
        if not isinstance(payload, list):
            errors.append(
                f"expected tuple/list return for {contract.name!r}, got {type(payload).__name__}"
            )
            return {}
        keys = list(contract.returns_schema)
        if len(payload) != len(keys):
            errors.append(
                f"{contract.name!r} returned {len(payload)} items, expected {len(keys)} ({keys})"
            )
            return {}
        return dict(zip(keys, payload, strict=True))

    # dict-shaped return
    if not isinstance(payload, dict):
        errors.append(f"expected dict return for {contract.name!r}, got {type(payload).__name__}")
        return {}
    return payload


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


def _rmtree_quiet(path: Path) -> None:
    """Best-effort recursive delete; swallow errors so cleanup never breaks
    a passing verification."""
    import contextlib
    import shutil

    with contextlib.suppress(OSError):
        shutil.rmtree(path, ignore_errors=True)
