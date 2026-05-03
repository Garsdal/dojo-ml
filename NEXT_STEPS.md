# NEXT_STEPS.md — Punch list for delivering MASTER_PLAN

> The MASTER_PLAN sets vision and abstractions. This file is the discrete, ordered work that gets us there.
> Read [MASTER_PLAN.md](MASTER_PLAN.md) first if you haven't.

---

## Handover note (read this if you're picking this up cold)

**Where we are:** Phases 0 → 3.5 are done and committed. Phase 4 is the current work — and it's a redesign of the contract layer, not a straight-line continuation of Phase 3.

**Why Phase 4 is a redesign:** Phase 3 built an anti-cheating contract on top of a *stdout-JSON convention* — AI-generated tools were Python scripts that printed JSON to stdout, and the MCP `evaluate` tool injected the agent's `y_pred` array (a list of thousands of floats) into the script as a Python literal at runtime. When we ran the California housing happy path against a real Claude agent, two failure modes surfaced:

1. **Wrapping was fragile.** Variable injection via `locals()[k] = v` produced NameError once the AI's generated tool code did `import x` between the injection and use. (Fixed in [src/dojo/runtime/tool_verifier.py](src/dojo/runtime/tool_verifier.py) with direct repr-based assignment, but the wrapping was a smell regardless.)
2. **The agent couldn't ship a 4128-element y_pred through tool-call parameters.** It burned 10+ Bash calls trying to extract `y_pred` from disk and feed it back into the `evaluate` MCP tool — gave up before reaching `evaluate`, `complete_experiment`, or `write_knowledge`. The full trace is preserved in this conversation's history; the punchline is that "agent passes y_pred to evaluate as a tool-call parameter" is fundamentally the wrong shape.

**The Phase 4 fix.** Three structural moves:

1. **Tools become real Python modules.** `load_data.py` defines `def load_data()`; `evaluate.py` defines `def evaluate(output)`. They live in the workspace pre-freeze, get copied to `.dojo/domains/{id}/tools/` at freeze (the canonical path), and imports at runtime resolve canonical first via `PYTHONPATH`.
2. **Agent's training code is a module that defines `def train()`.** It returns a task-specific output (for regression: `y_pred` as a list of floats). No `predictions.json`. No bulk data on disk. The contract generalises to other task types — only the return shape of `train()` and `evaluate()` changes.
3. **A framework-owned runner runs everything in one subprocess.** The runner is a 3-line stub the framework writes alongside the agent's code: `from train import train; from evaluate import evaluate; metrics = evaluate(train()); print("__DOJO_METRICS__:" + json.dumps(metrics))`. Train and evaluate execute in the same Python process — `y_pred` never leaves memory. The framework parses the marker line out of stdout and records the metrics dict (~100 bytes, not thousands of floats).

**Net effect:** **two MCP calls per experiment** (`run_experiment` → `write_knowledge`), no literal injection, no fixture wrapping, no `predictions.json` IPC. `run_experiment` collapses what used to be `create_experiment + run_experiment_code + evaluate + complete_experiment` into a single framework-driven step: it creates the experiment, writes the agent's train code + the runner into the sandbox, executes, parses metrics from the stdout marker, records them on the experiment, calls `tracking.log_metrics`, and transitions state. Anti-cheating becomes structurally bulletproof — the agent never handles bulk data or computes the metric.

**What this means for existing Phase 3 code:** parts get reworked. The list:

- [src/dojo/runtime/tool_verifier.py](src/dojo/runtime/tool_verifier.py) — verifier rewrites to use `importlib` instead of script execution. The whole `_wrap_for_execution` / fixture-injection mechanism goes away. `verify_required_tools` is restructured.
- [src/dojo/tools/domain_tools.py](src/dojo/tools/domain_tools.py) — currently registers each domain's `load_data` / `evaluate` as MCP tools so the agent can call them directly. Goes away. The per-domain frozen tools become plain Python modules; only the runner imports them. Platform MCP tools (`run_experiment`, `write_knowledge`, …) are unaffected — that's still the agent's interface.
- [src/dojo/tools/experiments.py](src/dojo/tools/experiments.py) — major rewrite. `create_experiment`, `run_experiment_code`, `complete_experiment`, `fail_experiment` are removed from the agent's MCP surface and folded into one new `run_experiment` tool. `get_experiment`, `list_experiments`, `compare_experiments` stay (read-side observability).
- [src/dojo/runtime/runner.py](src/dojo/runtime/runner.py) — **new file.** Owns the runner template and the metric-parsing logic. Single source of truth for "how does the framework run an experiment". Runtime-agnostic — only assumes Python + `Sandbox.execute()`.
- [src/dojo/agents/prompts.py](src/dojo/agents/prompts.py) — `_build_task_section` and the main `## Available tools` block both rewrite around the two-tool sequence. The "DO NOT use Bash to install packages" block goes away (with one execution tool there's no Bash conflict left).
- [src/dojo/runtime/task_service.py](src/dojo/runtime/task_service.py) — `freeze` gains the responsibility of copying tool modules to canonical path + storing SHA-256 hashes.
- [src/dojo/core/task.py](src/dojo/core/task.py) regression prompt template — rewrites so the AI generates Python modules with named functions. `ToolContract` semantics shift to "function signature + return shape". Add a `train_output_description` seam on `TaskTypeSpec` so adding CLASSIFICATION later is registry work, not runner work.
- [src/dojo/core/domain.py](src/dojo/core/domain.py) `DomainTool` — gains `entrypoint: str` (function name) and `module_filename: str` (e.g. `evaluate.py`). The `code: str` field stays for convenience but the canonical source is the file on disk. Drop `executable: bool` and `parameters` (stdout-JSON-era).
- [src/dojo/tools/tool_generation.py](src/dojo/tools/tool_generation.py) — parses module + function name from generated output instead of stdout-JSON scripts.

**Where to start:** Phase 4a in this document. The sub-phases (4a → 4g) are ordered so each leaves the codebase in a working state. Run `just test && just lint` after each one. The natural checkpoint is after 4c — the two-tool experiment loop works end-to-end with the stub backend.

**Final validation:** Phase 4g is the California housing manual integration test against real Claude. Don't ship Phase 4 until that's green.

---

## Highest-priority constraint: CLI-first

**Everything below is structured so the CLI is a peer entrypoint to the runtime, not a thin client of the HTTP API.**

The full happy path must be runnable from the terminal alone, with a running server optional:

```bash
mkdir /tmp/dojo-housing && cd /tmp/dojo-housing
dojo init --name housing --task-type regression --non-interactive
$EDITOR PROGRAM.md            # describe the dataset + goal in plain English
dojo task setup               # AI generates load_data.py + evaluate.py, verifies, freezes
dojo run --max-turns 30
```

Frontend and HTTP API stay supported, but they are *peers* of the CLI, not prerequisites for it. CLI commands call `LabEnvironment` services directly (the same services routers use), no `httpx` round-trips.

### CLI design conventions

| Convention | Rule |
|---|---|
| **Current domain** | `.dojo/state.yaml` holds `current_domain_id` (git's `HEAD` analogue). All CLI commands operate on it unless `--domain <name|id>` overrides. `dojo init` sets it; `dojo domain use <name>` switches it. |
| **PROGRAM.md** | Karpathy-style human-editable steering prompt. Default location `<workspace>/PROGRAM.md`. `Domain.program_path` field stores the override. At agent run start, file content (if present) wins over the in-storage `Domain.prompt`. |
| **Service access** | CLI commands import services from `dojo.runtime.*` and instantiate adapters via `dojo.api.deps.build_lab(settings)`. No HTTP. |
| **Output** | `rich` for human-formatted output. `--json` flag on read commands for scripting. |
| **Non-interactive mode** | Every interactive command accepts `--non-interactive` plus the same prompts as flags. CI and docs must work without TTY. |
| **Exit codes** | `0` success, `1` user error, `2` system error, `3` task-not-frozen / contract-violation. |

### Phases mirror MASTER_PLAN §9

- Phase 0 ✅ — Cleanup
- Phase 1 ✅ — Task abstraction + disk as single source of truth
- Phase 2 ✅ — CLI happy path (`dojo init` / `dojo run`) + PROGRAM.md convention
- Phase 3 ✅ — Tool verification + anti-cheating run gating (stdout-JSON contract)
- Phase 3.5 ✅ — Natural-language happy path (PROGRAM.md as the spec)
- **Phase 4 (in progress)** — Function-based contract + framework-owned evaluation. Replaces parts of Phase 3.
- Phase 5 — Reconnaissance

Don't move on to phase N+1 with phase N half-finished — the abstractions need to land cleanly.

---

## Phase 0 — Cleanup ✅

- [x] **Delete or rewrite `AGENTS.md`.** ✅ Deleted. README points at `CLAUDE.md` and `NEXT_STEPS.md`.
- [x] **Reclaim or delete legacy `dojo run "prompt"`.** ✅ Old `/tasks` HTTP poster replaced; `dojo run` rebuilt in Phase 2.
- [x] **Delete legacy frontend Task code.** ✅ `taskId` → `domainId` in `use-experiments.ts`.
- [x] **Audit `docs/`.** ✅ 15 superseded plans deleted.
- [x] **Unify Claude auth path.** ✅ `backend.complete()` shells out to `claude -p` — no `ANTHROPIC_API_KEY` needed.

---

## Phase 1 — Task abstraction + disk as source of truth ✅

### 1a — Disk as the single source of truth

- [x] **`RunStore` interface + `LocalRunStore`.** ✅ Files at `.dojo/runs/{id}.json`.
- [x] **Orchestrator writes through.** ✅ Every status change + every 10 events.
- [x] **Agent router cache.** ✅ `_runs` dict is a write-through cache; falls back to disk on miss.
- [x] **SSE event stream.** ✅ Falls back to persisted state.
- [ ] **Cross-process visibility test (deferred to Phase 4h).** Unit tests for `LocalRunStore` round-trip landed; the full two-process E2E test is held until Phase 4h.

### 1b — Task abstraction in core

- [x] **`core/task.py`** ✅ `TaskType` (REGRESSION only), `Direction`, `ToolContract`, `TaskTypeSpec`, `Task` (with `frozen: bool`), `TASK_TYPE_REGISTRY`.
- [x] **`Domain.task: Task | None`** + `program_path: str | None`. (Note: `Domain.tools` field still exists alongside `Task.tools` for backward compat. Phase 4 will likely drop it.)
- [x] **`storage/local/domain.py`** — full Task round-trip.
- [x] **`runtime/task_service.py`** — `create`, `get`, `update_config`, `freeze`, `unfreeze`, `delete`, `assert_ready`. `TaskNotReadyError` / `TaskFrozenError` / `TaskVerificationError`.
- [x] **HTTP routes** — six new endpoints under `/domains/{id}/task`.
- [x] **Tests** — 14 tests in `tests/unit/test_task_service.py`.

---

## Phase 2 — CLI happy path + PROGRAM.md convention ✅

- [x] **`cli/state.py`** — `.dojo/state.yaml` (`current_domain_id`, `current_run_id`) + `resolve_domain` helper.
- [x] **`cli/_lab.py`** — `build_cli_lab()` for in-process CLI commands.
- [x] **`runtime/program_loader.py`** — `resolve_program_path`, `load_program`, `write_program`, `default_program_template`. Orchestrator calls `load_program` at run start.
- [x] **`cli/init.py`** — interactive + flag-driven setup wizard.
- [x] **`cli/run.py`** — in-process agent run; streams events live to terminal; persists via `lab.run_store`.
- [x] **`cli/task.py`** — `show / generate / freeze / unfreeze / setup`.
- [x] **`cli/runs.py`** — `ls / show` with `--json`.
- [x] **`cli/program.py`** — `show / edit`.
- [x] **`cli/domain.py`** — added `use` and `current` so error messages are actionable.
- [x] **`cli/main.py`** — registers all subcommands.

---

## Phase 3 — Tool verification + anti-cheating run gating ✅

> **Note:** the contract design here will be partially reworked in Phase 4. The verification gate, freeze-time enforcement, and run-start gate stay; the *mechanics* of how tools are described, verified, and called change. Specifically: the stdout-JSON convention is replaced by Python modules with named functions.

### 3a — Tool verification

- [x] **`runtime/tool_verifier.py`** — `ToolVerifier.verify(tool, contract, workspace, fixtures, raw_output)` runs the tool in `LocalSandbox`, parses stdout JSON. **Phase 4a will rewrite this to use `importlib` instead of script execution.**
- [x] **`DomainTool.verification: VerificationResult | None`** — round-trips through storage.
- [x] **Registry-aware tool generation** — `build_task_generation_prompt(domain, task, hint, *, program_md="")`.
- [x] **HTTP and CLI generate paths** — both run the verifier and persist verification status.
- [x] **Freeze gate** — `TaskService.freeze` raises `TaskVerificationError` (HTTP 422 / CLI exit 3). Override: `--unsafe-skip-verify` / `?skip_verification=true`.

### 3b — Anti-cheating run gating

- [x] **`orchestrator.start`** calls `assert_ready` before backend.configure.
- [x] **`tools/server.py`** + **`domain_tools.py`** — `collect_all_tools` reads from `domain.task.tools`. **Phase 4d will drop per-domain tool registration entirely.**
- [x] **`agents/prompts.py`** — `_build_task_section` framing the contract. **Phase 4e rewrites this around the four-tool-call sequence.**
- [x] **`POST /agent/run`** — requires `domain_id`; returns 422 with `{kind: "task_not_ready"}` if not ready.
- [x] **`dojo run`** — surfaces `TaskNotReadyError` cleanly, exits 3.
- [x] **`complete_experiment`** — rejects metric keys outside `task.config["expected_metrics"]`. **Phase 4d makes `complete_experiment` internal-only.**

---

## Phase 3.5 — Natural-language happy path (PROGRAM.md as the spec) ✅

- [x] **`cli/init.py` slimmed** — `--data-path` / `--target-column` are optional; auto tool generation removed (deferred to `dojo task setup`).
- [x] **`build_task_generation_prompt(program_md=...)`** — threads PROGRAM.md content into the regression prompt template.
- [x] **Regression prompt template rewritten** — frames structured fields as optional, tells the model PROGRAM.md is the source of truth, requires `random_state=42`.
- [x] **PROGRAM.md template refreshed** — `## Dataset` / `## Target` / `## Success` sections.
- [x] **CLI + HTTP generate callers thread PROGRAM.md** — both load PROGRAM.md and pass it into the prompt builder.
- [x] **`dojo task setup` bug fix** — extracted `_do_generate` / `_do_freeze` async helpers so `setup` doesn't leak typer-OptionInfo defaults into `generate`. Spinners + model name visibility added.

---

## Phase 4 — Function-based contract + framework-owned evaluation

> **The redesign that grounds the rest of the project.** Replaces the stdout-JSON contract from Phase 3 with a Python-module contract. Tools become real importable modules; a framework-owned runner runs train + evaluate in one subprocess; the agent's per-experiment surface shrinks to two MCP calls. Read the **Handover note** at the top of this file for context on why.

### Design — the two-tool experiment loop

Every experiment is exactly two MCP tool calls:

| # | Tool | What happens |
|---|---|---|
| 1 | `run_experiment(domain_id, hypothesis, train_code, variables=?)` | Creates the experiment (PENDING → RUNNING), writes `train_code` + the runner into the sandbox, executes via `Sandbox.execute()`, parses the `__DOJO_METRICS__:` marker out of stdout, validates metric keys against `task.config["expected_metrics"]`, records `experiment.result.metrics`, calls `tracking.log_metrics`, transitions to COMPLETED (or FAILED on `__DOJO_ERROR__:` / non-zero exit). Returns `{experiment_id, status, metrics, stdout, stderr, exit_code, run_number}`. |
| 2 | `write_knowledge(experiment_id, claim, ...)` | Records the learning. |

Read-only observability tools — `get_experiment`, `list_experiments`, `compare_experiments`, `search_knowledge`, `list_knowledge` — stay available. `log_metrics` / `log_params` stay as **optional** tools the agent can call to log intermediate values during `train()` (e.g. per-epoch loss curves); they are no longer required for the experiment-final metric. `create_experiment`, `complete_experiment`, `fail_experiment`, `run_experiment_code`, `evaluate_experiment` are **all gone** from the agent's surface — the framework drives those transitions inside `run_experiment`.

### Tools are Python modules with named functions

Pre-freeze the AI generates two files in the workspace:

```python
# load_data.py — the user reviews this before approving
from sklearn.datasets import fetch_california_housing
from sklearn.model_selection import train_test_split

def load_data():
    X, y = fetch_california_housing(return_X_y=True)
    return train_test_split(X, y, test_size=0.2, random_state=42)
```

```python
# evaluate.py
import numpy as np
from sklearn.metrics import mean_squared_error, r2_score, mean_absolute_error
from load_data import load_data

def evaluate(y_pred):
    _, _, _, y_test = load_data()
    return {
        "rmse": float(np.sqrt(mean_squared_error(y_test, y_pred))),
        "r2":   float(r2_score(y_test, y_pred)),
        "mae":  float(mean_absolute_error(y_test, y_pred)),
    }
```

### Agent's training code: a module that defines `train()`

The `train_code` passed to `run_experiment` is a Python module string that defines `def train()` returning the task-specific output. For regression: a list/array of floats (`y_pred`).

```python
from load_data import load_data
from sklearn.linear_model import LinearRegression

def train():
    X_train, X_test, y_train, _ = load_data()
    model = LinearRegression().fit(X_train, y_train)
    return model.predict(X_test).tolist()
```

The agent never imports `evaluate`, never writes `predictions.json`, never sees `y_test` in any meaningful way (load_data returns it but the contract says don't peek — the system prompt enforces this socially; structurally the agent could cheat but evaluate is canonical and the metric still comes from there).

### The runner — single source of truth for "how does an experiment run"

The framework writes a tiny stub alongside the agent's code in the sandbox:

```python
# __dojo_runner.py — owned by [src/dojo/runtime/runner.py](src/dojo/runtime/runner.py)
import json, sys, traceback
try:
    from __dojo_train_{run_number} import train
    from evaluate import evaluate
    metrics = evaluate(train())
    print("__DOJO_METRICS__:" + json.dumps(metrics))
except Exception as e:
    print("__DOJO_ERROR__:" + json.dumps({
        "type": type(e).__name__, "message": str(e), "traceback": traceback.format_exc(),
    }))
    sys.exit(1)
```

`train()` and `evaluate()` execute in the same Python process — `y_pred` lives in memory only, never persisted. The marker line on stdout is the IPC mechanism: ~100 bytes of JSON, easy to grep, robust to any other prints `train()` does. The runner is the only piece that bridges "inside the sandbox subprocess" with "outside, where the framework records metrics".

This is also the **runtime-portability boundary**: switching from `LocalSandbox` to a Docker or remote sandbox later is a new `Sandbox` impl. The runner, frozen tools, and agent contract are unchanged.

### Canonical tool path

| Stage | `load_data.py` / `evaluate.py` location |
|---|---|
| Pre-freeze (after `dojo task generate`) | `<workspace>/load_data.py` — visible to the user, editable |
| Frozen (after `dojo task freeze`) | `.dojo/domains/{domain_id}/tools/load_data.py` — canonical, immutable |

At runtime, `run_experiment` invokes the sandbox with `PYTHONPATH = <canonical_dir>:<workspace>` and cwd `<workspace>`, so `from evaluate import evaluate` always resolves canonical first. The agent overwriting workspace `evaluate.py` is a no-op for the recorded metric.

### Generalisation hook (don't build, just leave the seam)

Add `TaskTypeSpec.train_output_description: str` (e.g. `"list of float predictions for the test set"`) and reference it from the regression generation prompt. When CLASSIFICATION lands later: new registry entry, new evaluate template, new prompt that says `train()` returns class labels. Runner unchanged. `run_experiment` unchanged. System prompt is parameterised on this.

### Sub-phases

#### 4a — Tools as Python modules + import-based verifier

**Files to change:**
- [src/dojo/core/task.py](src/dojo/core/task.py) — rewrite the regression `generation_prompt_template`. AI must produce two **modules** with named functions: `load_data.py` defining `def load_data()`, `evaluate.py` defining `def evaluate(y_pred)`. Output format becomes a JSON array with `{name, filename, entrypoint, code}` per tool. Add `TaskTypeSpec.train_output_description`.
- [src/dojo/core/domain.py](src/dojo/core/domain.py) — add `DomainTool.entrypoint: str = ""` (function name) and `DomainTool.module_filename: str = ""` (e.g. `evaluate.py`). Drop `executable: bool` and `parameters` (stdout-JSON-era — see 4e).
- [src/dojo/storage/local/domain.py](src/dojo/storage/local/domain.py) — round-trip the new fields.
- [src/dojo/tools/tool_generation.py](src/dojo/tools/tool_generation.py) `parse_generated_tools` / `dicts_to_domain_tools` — populate `entrypoint` and `module_filename` from the AI's output.
- [src/dojo/runtime/tool_verifier.py](src/dojo/runtime/tool_verifier.py) — full rewrite:
  - Drop `_wrap_for_execution`, `_safe_script_filename` for verifier use, fixture-literal injection.
  - To verify: write the tool's code to a tempdir, spawn a subprocess that does `import importlib.util; spec = importlib.util.spec_from_file_location(name, path); mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); result = getattr(mod, entrypoint)(**fixtures); print(json.dumps(result))`. Parse the result, validate against `ToolContract.returns_schema`. Subprocess for isolation (so the verifier doesn't leak imports into the dojo process).
  - For regression: verify `load_data` first (no fixtures); use its `y_test` output as `y_pred` fixture for `evaluate` verification.
- Tests: rewrite the verifier tests to assert import-based round-trip (good module verifies, bad module fails with clear error).

#### 4b — Canonical tool path on freeze

**Files to change:**
- [src/dojo/runtime/task_service.py](src/dojo/runtime/task_service.py) `freeze`:
  - For each tool in `task.tools`: copy `<workspace>/<module_filename>` to `.dojo/domains/{domain_id}/tools/<module_filename>`. Compute SHA-256 hash. Store hashes on `task.config["tool_hashes"] = {"load_data.py": "...", "evaluate.py": "..."}`.
  - Reject freeze if a tool's `module_filename` is missing from the workspace (clear error: "evaluate.py not found in workspace; run `dojo task generate` to recreate it").
  - `assert_ready` additionally verifies `tool_hashes` match canonical files (defence-in-depth — detects tampering with the canonical dir).
- [src/dojo/cli/task.py](src/dojo/cli/task.py) `_do_generate` — write generated module files to the workspace (not just to in-memory `DomainTool.code`). Update the success message to point the user at the generated files.

#### 4c — Runner module + `run_experiment` MCP tool

**New file:** [src/dojo/runtime/runner.py](src/dojo/runtime/runner.py)
- Owns `RUNNER_TEMPLATE` (the stub shown above, parameterised on `train_module` name).
- Owns `parse_runner_stdout(stdout: str) -> RunnerOutcome` — finds `__DOJO_METRICS__:` or `__DOJO_ERROR__:` markers; returns a typed result `{kind: "metrics", metrics} | {kind: "error", error_dict} | {kind: "no_marker"}`.
- This module is the single source of truth for "how an experiment is shaped". Sandbox-agnostic.

**Files to change:**
- [src/dojo/tools/experiments.py](src/dojo/tools/experiments.py) — major rewrite:
  - **New tool: `run_experiment(domain_id, hypothesis, train_code, variables=None)`**:
    1. Create the experiment record (PENDING → RUNNING) via `ExperimentService`.
    2. Compute `run_number` (always 1 in the new model — see note below).
    3. Save `train_code` to `.dojo/artifacts/experiments/{exp_id}/__dojo_train_{run_number}.py` (artifact provenance) AND to `<workspace>/__dojo_train_{run_number}.py` (sandbox import path).
    4. Render runner from `RUNNER_TEMPLATE` and write to `<workspace>/__dojo_runner.py`.
    5. Call `lab.sandbox.execute(...)` with cwd=workspace, `python_path=workspace.python_path`, `PYTHONPATH=<canonical_tools>:<workspace>`, entry point `python __dojo_runner.py`.
    6. Run `parse_runner_stdout(exec_result.stdout)`:
       - `metrics` → validate keys against `task.config["expected_metrics"]`; set `experiment.result.metrics`; call `tracking.log_metrics`; transition to COMPLETED.
       - `error` → set `experiment.result.error`; transition to FAILED.
       - `no_marker` (e.g. exit_code != 0 with no marker) → record stdout/stderr as the error; transition to FAILED.
    7. Append a `CodeRun` record to `experiment.result.code_runs`.
    8. Return `{experiment_id, status, metrics, stdout, stderr, exit_code, run_number}`.
  - **Drop from MCP surface (delete from the returned `ToolDef` list):** `create_experiment`, `complete_experiment`, `fail_experiment`, `run_experiment_code`. Keep the underlying service methods on `ExperimentService` since `run_experiment` and the HTTP routes still call them internally.
  - Keep `get_experiment`, `list_experiments`, `compare_experiments` exactly as today.
  - Note on run_number: in the new model, every `train_code` submission is its own experiment (a new hypothesis test). If the agent wants to retry broken code, they call `run_experiment` again with the same hypothesis text — cheap, clean, no debug pollution under one experiment ID. Run number stays in the artifact path for forward-compat but is always 1 today.
- [src/dojo/tools/server.py](src/dojo/tools/server.py) `collect_all_tools`:
  - **Drop `create_domain_tools(lab, domain)`** — the per-domain frozen tools (`load_data`, `evaluate`) are no longer registered as MCP tools. They live as plain Python modules at `.dojo/domains/{id}/tools/` and are imported by the runner inside `run_experiment`, not invoked by the agent.
  - The agent's MCP surface is exactly: `run_experiment`, `write_knowledge`, `search_knowledge`, `list_knowledge`, `get_experiment`, `list_experiments`, `compare_experiments`, `log_metrics` (optional), `log_params` (optional). Plus the built-in Claude `Bash`, `Read`, `Write`, `Edit`, `WebFetch`.

#### 4d — System prompt rewrite

**Files to change:**
- [src/dojo/agents/prompts.py](src/dojo/agents/prompts.py) `build_system_prompt` + `_build_task_section`:
  - Replace the full `## Available tools` block. Show the shrunken surface above (per-experiment vs read-only vs optional).
  - Drop the entire "Code execution — IMPORTANT / DO NOT use Bash to install packages …" section. With one execution tool there's no Bash conflict to warn about.
  - The new workflow becomes:
    1. `search_knowledge` — what do we already know?
    2. Plan a hypothesis.
    3. `run_experiment(domain_id, hypothesis, train_code)` — train_code defines `def train()` returning predictions.
    4. `write_knowledge` — record what you learned.
    5. After 2+ experiments, `compare_experiments` to assess progress.
  - Show one inline `train.py` example with `def train()`.
  - In `_build_task_section`: frame the contract as "the framework runs your `def train()` against frozen `load_data` and `evaluate`. You only own `train()`." List `train_output_description` from the registry inline so future task types reuse the section.

#### 4e — Cleanup of stranded Phase 3 code

- Drop `Domain.tools` field; `domain.task.tools` is the only source. Audit frontend response shape and update `use-domains.ts`.
- Drop `DomainTool.executable: bool` and `DomainTool.parameters` (stdout-JSON-era — superseded by `entrypoint` + `module_filename`).
- Delete [src/dojo/tools/domain_tools.py](src/dojo/tools/domain_tools.py) entirely once `collect_all_tools` no longer references it. Drop the `_normalize_params` helper with it.
- Drop fixture-injection paths from [src/dojo/runtime/tool_verifier.py](src/dojo/runtime/tool_verifier.py) (already done structurally in 4a; this is the "no dead code left" pass).
- Verifier writes to a tempdir, not the workspace. Cleanup automatic.
- The user's workspace ends up with `load_data.py`, `evaluate.py`, `PROGRAM.md`, plus whatever the agent's last `__dojo_train_*.py` and `__dojo_runner.py` were (overwritten each run). No `predictions.json`, no metric files.
- Update [README.md](README.md) "Getting Started" if any commands changed.

#### 4f — Tests

- **Verifier import-based round-trip** ([tests/unit/test_tool_verifier.py](tests/unit/test_tool_verifier.py)) — rewrite. Test cases:
  - Good module verifies: `load_data()` returns 4-tuple, `evaluate(y_pred)` returns `{rmse, r2, mae}`.
  - Module is missing the entrypoint → fails with clear error.
  - Function raises → caught, error includes the exception message.
  - Wrong return shape → fails with key-mismatch message.
- **Runner round-trip** (new — `tests/unit/test_runner.py`):
  - `parse_runner_stdout` finds `__DOJO_METRICS__:` line and returns metrics.
  - `parse_runner_stdout` finds `__DOJO_ERROR__:` line and returns the error dict.
  - Multiple lines / interleaved prints from `train()` don't confuse the parser (it scans for the marker line).
  - No marker → `no_marker` outcome.
- **Canonical path enforcement** (new — `tests/integration/test_canonical_tools.py`):
  - Generate + freeze → tool files in `.dojo/domains/{id}/tools/`. Hashes stored.
  - Tamper with canonical `evaluate.py` → `assert_ready` fails.
  - Overwrite workspace `evaluate.py` → `run_experiment` still uses canonical → recorded metric matches the canonical version's output.
- **Two-tool E2E with stub agent** (new — `tests/integration/test_phase4_experiment_loop.py`):
  - Stub generates predictable `train()` code, calls `run_experiment`, asserts metrics on response and on `experiment.result.metrics`.
  - Stub generates broken code (raises in `train()`), asserts FAILED state and traceback in error.
  - Stub generates code with no `train()` function, asserts ImportError surfaces clearly.
- **Tracking integration** — `run_experiment` calls `tracking.log_metrics` once on success. Verify with `FileTracker` round-trip.
- **MCP surface contract** — `collect_all_tools(lab, domain)` returns exactly the names listed in 4c. No `create_experiment` / `complete_experiment` / etc. exposed.

#### 4g — California housing end-to-end (final validation)

This is the validation gate. Don't merge Phase 4 until this is green.

- **Reproduce the full happy path from a clean dir:**
  ```bash
  mkdir /tmp/dojo-housing && cd /tmp/dojo-housing
  dojo init --name housing --task-type regression --non-interactive
  $EDITOR PROGRAM.md            # use the example below
  dojo task setup               # AI generates load_data.py + evaluate.py, verifies, freezes
  dojo run --max-turns 30
  ```

  Reference `PROGRAM.md`:
  ```markdown
  ## Goal
  Predict California median house value (regression) — minimise RMSE on a 20% held-out test split.

  ## Dataset
  Use `sklearn.datasets.fetch_california_housing(return_X_y=True)`.
  Features and target both come back as numpy arrays — no column names needed.
  https://scikit-learn.org/stable/modules/generated/sklearn.datasets.fetch_california_housing.html

  ## Success
  Beat a linear baseline. Try at least one tree-based model. Avoid overfitting.
  ```

- **Observe**: every experiment has a metric, the metrics are comparable, the agent's `train()` body varies, the evaluator code does not. Per experiment: one `run_experiment` call, one `write_knowledge` call. No Bash spirals, no `predictions.json` on disk.
- **Replay test.** Re-execute `.dojo/artifacts/experiments/{id}/__dojo_train_1.py` directly: write a quick replay script that imports the agent's `train` and the canonical `evaluate`, runs both, prints metrics. Should match the recorded metric.
- **Cheating test.** Manually overwrite `<workspace>/evaluate.py` with a version that always returns `{"rmse": 0.0, "r2": 1.0, "mae": 0.0}`. Run `dojo run` — recorded metric must come from the canonical `.dojo/domains/{id}/tools/evaluate.py`, not the tampered workspace copy. Verify via `dojo runs show <id>`.
- **Knowledge accumulation test.** Start a *second* `dojo run` on the same domain. The system prompt should include accumulated knowledge from the first run (logged to `.dojo/runs/{id}/system_prompt.txt` if missing — add it). The agent should visibly use it.
- **No-server test.** Run the full path with no `dojo start` in another terminal — everything works in-process.
- **Cross-process visibility test.** While `dojo run` is in flight from terminal A, run `dojo start` in terminal B and curl `/agent/runs/{id}` — the in-flight CLI run is visible, with up-to-date events. (This satisfies the deferred Phase 1a test.)

**Done when:** all six points pass *and* the two-tool experiment loop is the only path metrics enter the system. This is the "Dojo actually works" milestone.

---

## Phase 5 — Reconnaissance for what's next

Don't start anything in this phase until Phase 4 is fully green.

- [ ] Decide if Knowledge linker needs an upgrade based on what real runs reveal. Keyword overlap may be enough; it may not.
- [ ] Decide if a wall-clock budget per experiment (Karpathy's "5 min compute budget") is needed. If experiments diverge wildly in runtime, yes.
- [ ] Audit the frontend against the new contract — task creation/freeze/verify is a real UX flow. Spec it before building. The CLI can stay primary; frontend is a complement.
- [ ] Get the first external user. The MASTER_PLAN success criteria say "3 real users outside Marcus" before considering the closed cloud layer; one is the first hurdle.

---

## What's *not* on this list

By design. If you find yourself wanting to add one of these, push back or add it explicitly via decision-log update in MASTER_PLAN.

- New `TaskType` members beyond `REGRESSION`
- Many-Tasks-per-Domain
- Multi-tenancy / SaaS / cloud sandbox
- New storage backends (Postgres, Supabase)
- Embedding-based knowledge search / agentic linker
- Wholesale frontend rewrite
- New agent backends (Copilot, ChatGPT, etc.)
- Distributed compute, MLflow operations features
- A separate REPL or web-based "init wizard" — the CLI *is* the wizard

These are all reasonable later, none are right *now*.

---

## Status snapshot (update as you go)

- [x] Phase 0 — Cleanup
- [x] Phase 1 — Task abstraction lands in core (disk as source of truth + Task/TaskService/RunStore)
- [x] Phase 2 — CLI happy path + PROGRAM.md convention
- [x] Phase 3 — Tool verification + anti-cheating run gating *(stdout-JSON contract — partially superseded by Phase 4)*
- [x] Phase 3.5 — Natural-language happy path (PROGRAM.md as the spec)
- [ ] Phase 4 — Function-based contract + framework-owned evaluation
  - [ ] 4a — Tools as modules + import-based verifier
  - [ ] 4b — Canonical tool path on freeze
  - [ ] 4c — Runner module + `run_experiment` MCP tool
  - [ ] 4d — System prompt rewrite
  - [ ] 4e — Cleanup of stranded Phase 3 code
  - [ ] 4f — Tests
  - [ ] 4g — California housing E2E (validation gate)
- [ ] Phase 5 — Reconnaissance
