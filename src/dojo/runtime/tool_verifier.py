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
from dojo.core.task import TASK_TYPE_REGISTRY, Task, ToolContract
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

        runner_script_path: Path | None = None
        try:
            (dir_path / module_filename).write_text(tool.code)

            runner = _build_verifier_runner(
                module_filename=module_filename,
                entrypoint=entrypoint,
                fixtures=params,
            )

            _cwd, python_path, env_vars = _workspace_args(workspace)
            runner_name = f"verify_{tool.name}"
            runner_script_path = dir_path / f"{runner_name}.py"

            start = time.monotonic()
            result = await self.sandbox.execute(
                runner,
                cwd=str(dir_path),
                python_path=python_path,
                env_vars=env_vars,
                timeout=self.timeout,
                name=runner_name,
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
                origin = _last_user_frame(error_payload.get("traceback") or "", module_filename)
                where = f" at {origin}" if origin else ""
                errors.append(f"{tool.name} raised{where}: {msg}")
                return VerificationResult(
                    verified=False,
                    errors=errors,
                    duration_ms=duration_ms,
                    verified_at=datetime.now(UTC),
                )

            result_payload = _scan_marker(stdout, _RESULT_MARKER)
            if result_payload is None:
                if result.exit_code != 0:
                    errors.append(_format_exit_error(tool.name, result, stderr, stdout))
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
            # The sandbox only auto-cleans script files when no cwd is given;
            # we always pass cwd, so delete the runner stub ourselves to
            # avoid leaving `verify_<tool>.py` next to the user's modules.
            if runner_script_path is not None:
                runner_script_path.unlink(missing_ok=True)
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
    module_dir: Path | None = None,
) -> list[DomainTool]:
    """Verify each required tool for `task` in dependency order.

    Lays out a single directory with every required tool's module file, so that
    ``evaluate.py`` can ``from load_data import load_data`` during its own
    verification. Mutates ``tools`` in place: every tool whose name matches a
    contract gets its ``verification`` field populated.

    When ``module_dir`` is given, modules are written there and the directory
    persists across calls — useful so tools like `load_data` can cache fetched
    datasets next to themselves and the next verification reuses the cache.
    When omitted, a fresh tempdir is created and torn down (used by tests and
    in-memory flows).

    Cascade behaviour: if a tool fails, downstream tools that depend on its
    output (e.g. evaluate depends on load_data) are skipped with a clear
    "skipped because <upstream> failed" error rather than the misleading
    "missing fixture" message.

    Returns the same list (for fluent use).
    """
    spec = TASK_TYPE_REGISTRY.get(task.type)
    if spec is None:
        return tools

    by_name = {t.name: t for t in tools}
    verifier = ToolVerifier(sandbox, timeout=timeout)
    raw_outputs: dict[str, dict[str, Any]] = {}
    failed_upstream: set[str] = set()

    if module_dir is not None:
        module_dir.mkdir(parents=True, exist_ok=True)
        # Resolve to absolute — the sandbox runs the verifier subprocess with
        # ``cwd=module_dir``, and the script path it executes is relative to
        # the parent's cwd, not the child's. A relative module_dir double-joins.
        module_dir = module_dir.resolve()
        await _verify_in_dir(
            module_dir, spec, by_name, verifier, workspace, raw_outputs, failed_upstream, task
        )
    else:
        with tempfile.TemporaryDirectory(prefix="dojo_verify_") as tmp:
            await _verify_in_dir(
                Path(tmp),
                spec,
                by_name,
                verifier,
                workspace,
                raw_outputs,
                failed_upstream,
                task,
            )

    return tools


async def _verify_in_dir(
    module_dir: Path,
    spec: Any,
    by_name: dict[str, DomainTool],
    verifier: ToolVerifier,
    workspace: Workspace | None,
    raw_outputs: dict[str, dict[str, Any]],
    failed_upstream: set[str],
    task: Task,
) -> None:
    """Run the per-contract verification loop against a fixed module directory."""
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

        upstream = _upstream_dep(spec, contract.name)
        if upstream and upstream in failed_upstream:
            tool.verification = VerificationResult(
                verified=False,
                errors=[
                    f"verification skipped — {upstream} must verify first "
                    f"(fix {upstream} and re-run)"
                ],
            )
            failed_upstream.add(contract.name)
            continue

        fixtures = _build_fixtures(spec, contract.name, raw_outputs)
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
        if not result.verified:
            failed_upstream.add(contract.name)


def _upstream_dep(spec: Any, tool_name: str) -> str | None:
    """Return the upstream tool whose output `tool_name` depends on, if any.

    The upstream name comes from ``TaskTypeSpec.verifier_dependencies[tool_name]``
    so adding a new task type is a registry-only change — no hardcoded names here.
    """
    return spec.verifier_dependencies.get(tool_name)


def _build_fixtures(
    spec: Any,
    tool_name: str,
    raw_outputs: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    """Map an upstream tool's outputs into fixtures for the current tool.

    Mapping comes from ``verifier_fixture_keys[tool_name]`` (param -> source key);
    the upstream tool name comes from ``verifier_dependencies[tool_name]``.
    Returns None when no mapping, no dependency declared, or the upstream output
    is missing.
    """
    mapping = spec.verifier_fixture_keys.get(tool_name)
    if not mapping:
        return None
    upstream_name = spec.verifier_dependencies.get(tool_name)
    if upstream_name is None:
        return None
    upstream = raw_outputs.get(upstream_name)
    if upstream is None:
        return None
    fixtures: dict[str, Any] = {}
    for param, source_key in mapping.items():
        if source_key not in upstream:
            return None
        fixtures[param] = upstream[source_key]
    # Truncate list fixtures before they are repr()'d into the verifier script
    # source. The verifier only checks that the function accepts the params and
    # returns the right keys — full-size dataset arrays embedded as Python
    # literals cause the subprocess to be killed (OOM) on large datasets.
    return {k: v[:5] if isinstance(v, list) else v for k, v in fixtures.items()}


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
    # numpy arrays + pandas Series → list via .tolist()
    if hasattr(value, "tolist") and callable(value.tolist):
        try:
            return _to_jsonable(value.tolist())
        except Exception:
            pass
    # pandas DataFrames + polars frames → numpy → list. DataFrames don't have
    # .tolist() directly, but to_numpy() gives a numpy array which does.
    if hasattr(value, "to_numpy") and callable(value.to_numpy):
        try:
            return _to_jsonable(value.to_numpy().tolist())
        except Exception:
            pass
    if isinstance(value, (tuple, list)):
        return [_to_jsonable(v) for v in value]
    if isinstance(value, dict):
        return {{k: _to_jsonable(v) for k, v in value.items()}}
    if isinstance(value, (bool, int, float, str)) or value is None:
        return value
    # Don't silently coerce unknown types to str(repr) — that produced the
    # `expected list, got str` confusion when a tool returned a DataFrame.
    # Fail loudly so the verifier reports something the user can act on.
    raise TypeError(
        f"verifier cannot JSON-encode {{type(value).__name__}} "
        f"(no .tolist() / .to_numpy() / list / dict / scalar) — "
        f"return numpy arrays, pandas/polars frames, or plain Python "
        f"containers from your tool"
    )


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


def _last_user_frame(traceback_text: str, module_filename: str) -> str | None:
    """Extract the last frame from a Python traceback that points at the
    generated tool module (e.g. ``evaluate.py:12``).

    Frames inside dojo's own runner stub or stdlib / third-party packages are
    skipped — we only want to point at the file the user (or AI) authored,
    so the error message can clearly say "fix this line in evaluate.py".
    """
    if not traceback_text:
        return None
    # Lines look like:  File "/abs/path/evaluate.py", line 12, in evaluate
    target = module_filename
    last: tuple[str, str] | None = None
    for line in traceback_text.splitlines():
        line = line.strip()
        if not line.startswith("File "):
            continue
        try:
            head, rest = line.split(",", 1)
            path = head[len('File "') : -1]
            line_no = rest.strip().split(",")[0].removeprefix("line ").strip()
        except (ValueError, IndexError):
            continue
        if path.endswith("/" + target) or path.endswith("\\" + target) or path == target:
            last = (target, line_no)
    if last is None:
        return None
    return f"{last[0]}:{last[1]}"


def _format_exit_error(tool_name: str, result: Any, stderr: str, stdout: str) -> str:
    """Build a human-readable error from a non-zero exit, with hints for
    well-known signal codes so users don't have to look up POSIX numbers."""
    detail = stderr.strip()[:500] or stdout.strip()[:500]
    code = result.exit_code
    hint = ""
    if code == -9 or code == 137:  # SIGKILL (137 = 128 + 9 in some shells)
        hint = (
            " — likely the OS killed it for using too much memory (SIGKILL). "
            "Try shrinking the dataset window in PROGRAM.md, or pre-build any "
            "expensive cache outside `dojo task setup` (run the file once with "
            "`uv run python <sources_dir>/load_data.py`)."
        )
    elif code == -15 or code == 143:  # SIGTERM
        hint = " — process was terminated (SIGTERM)."
    elif result.stderr and "Execution timed out" in result.stderr:
        hint = (
            " — verification timed out. Bump the cap with "
            "`dojo task setup --timeout <seconds>` or pre-build the cache."
        )
    suffix = f": {detail}" if detail else ""
    return f"{tool_name} exited with code {code}{hint}{suffix}"


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
        # Empty arrays are always wrong for training/test splits — they pass
        # the type check but produce confusing downstream errors (sklearn
        # crashes inside evaluate with "Found array with 0 sample(s)"). Catch
        # it here with a message that points at the actual cause.
        if not value:
            return (
                "expected a non-empty list, got []. "
                "Your data loader returned 0 rows — likely the dataset window "
                "in PROGRAM.md (FETCH_START/FETCH_END, filters, etc.) "
                "produced no matching rows. Inspect the cache or widen the window"
            )
        if "list of list" in s and not isinstance(value[0], list):
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
