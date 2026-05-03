# NEXT_STEPS.md — Punch list for delivering MASTER_PLAN

> The MASTER_PLAN sets vision and abstractions. This file is the discrete, ordered work that gets us there.
> Read [MASTER_PLAN.md](MASTER_PLAN.md) first if you haven't.

## Highest-priority constraint: CLI-first

**Everything below is structured so the CLI is a peer entrypoint to the runtime, not a thin client of the HTTP API.**

The full happy path must be runnable from the terminal alone, with a running server optional:

```bash
dojo init             # interactive: config + workspace + task + AI tool gen + verify + freeze
$EDITOR PROGRAM.md    # iterate on the steering prompt
dojo run              # agent runs on the current domain; events stream to terminal
```

Frontend and HTTP API stay supported, but they are *peers* of the CLI, not prerequisites for it. CLI commands call `LabEnvironment` services directly (the same services routers use), no `httpx` round-trips. This mirrors the existing pattern in [`cli/domain.py`](src/dojo/cli/domain.py) where `_create_domain` calls `LocalDomainStore` and `WorkspaceService` directly.

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

- Phase 0 — Cleanup
- Phase 1 — Task abstraction lands in core + disk becomes the single source of truth for runs (load-bearing for CLI-first; no CLI commands yet)
- Phase 2 — CLI happy path (`dojo init` / `dojo run`) + PROGRAM.md convention
- Phase 3 — Tool verification + anti-cheating run gating (the "make the contract real" phase)
- Phase 4 — End-to-end RegressionTask validated entirely from the terminal
- Phase 5 — Recon

Don't move on to phase N+1 with phase N half-finished — the abstractions need to land cleanly.

---

## Phase 0 — Cleanup (do first; fast)

Pre-existing cruft that the rewrite would otherwise have to navigate around. None of these are big.

- [x] **Delete or rewrite `AGENTS.md`.** ✅ Deleted. README points at `CLAUDE.md` and `NEXT_STEPS.md`.
- [x] **Reclaim or delete legacy `dojo run "prompt"`.** ✅ Old `/tasks` HTTP poster replaced with a placeholder that exits with a clear "Phase 2 will rebuild this" message.
- [x] **Delete legacy frontend Task code.** ✅ No standalone task pages existed. Only `taskId` param in `use-experiments.ts` — replaced with `domainId` / `?domain_id=`.
- [x] **Audit `docs/`.** ✅ 15 superseded plans deleted. `docs/archive/end-to-end-agent-harness-v2.md` kept as historical reference.
- [x] **Unify Claude auth path.** ✅ `backend.complete()` now shells out to `claude -p <prompt>` — same auth path as agent runs, no `ANTHROPIC_API_KEY` needed. See [`agents/backends/claude.py:117-138`](src/dojo/agents/backends/claude.py#L117-L138).
**Done when:** `git ls-files docs/` shows only current docs, frontend builds clean, one Claude auth path, no broken `dojo run` command in the user's shell history.

> Note: reconciling the in-memory `_runs` dict to be a write-through cache over disk used to live here, but it's load-bearing for the CLI-first claim — moved to Phase 1 (1a).

---

## Phase 1 — Task abstraction lands in core (and disk becomes the source of truth)

Introduce the typed Task in the data layer. Domain has-one Task. `RegressionTask` is the only TaskType. **No CLI changes in this phase** — services and storage land first so the Phase 2 CLI commands have something to call.

### 1a — Disk as the single source of truth (load-bearing for CLI-first)

The whole "CLI is a peer of the server" claim falls apart if a CLI-started run is invisible to a separately-running server (or another CLI invocation). So before any new abstractions land, fix this:

- [x] **`RunStore` interface + `LocalRunStore`.** ✅ Lives at [`interfaces/run_store.py`](src/dojo/interfaces/run_store.py) and [`storage/local/run.py`](src/dojo/storage/local/run.py). Files at `.dojo/runs/{id}.json`. Full deserialisation of nested types (events, config, result, hints).
- [x] **`src/dojo/agents/orchestrator.py`** — ✅ Writes through on run start, every 10 events, every status change, and on completion / failure / exception.
- [x] **`src/dojo/api/routers/agent.py`** — ✅ `_runs` dict is now a write-through cache; `list_runs`, `get_run`, and the SSE stream fall back to `lab.run_store` when the cache misses.
- [x] **SSE event stream** — ✅ Falls back to persisted state when the run isn't in the in-process cache.
- [ ] **Cross-process visibility test (deferred to Phase 4 §"Cross-process visibility test").** Unit tests for `LocalRunStore` round-trip landed (11 tests in [`tests/unit/test_run_store.py`](tests/unit/test_run_store.py)); the full two-process E2E test is held until Phase 4 because it requires the CLI command to exist.

**Done when:** any process can see any other process's runs, given the same `.dojo/` directory. The in-memory dict is either a cache or gone.

### 1b — Task abstraction in core

- [x] **`src/dojo/core/task.py`** ✅ Defines `TaskType` (`REGRESSION` only), `Direction`, `ToolContract`, `TaskTypeSpec`, `Task` (with `frozen: bool`), and `TASK_TYPE_REGISTRY` with the full regression entry including a generation prompt template.
- [x] **`src/dojo/core/domain.py`** — ✅ Added `task: Task | None = None` and `program_path: str | None = None`. Deviation from spec: kept `tools: list[DomainTool]` for backward compat (existing endpoints, tests, and frontend). The migration to "tools live only on Task" is deferred to Phase 3 alongside anti-cheating wiring.
- [x] **`src/dojo/storage/local/domain.py`** — ✅ `_task_from_dict` handles Task deserialisation; missing fields default to `None`.
- [x] **`src/dojo/runtime/task_service.py`** — ✅ `create`, `get`, `update_config`, `freeze`, `unfreeze`, `delete`, `assert_ready`. Plus `TaskNotReadyError` and `TaskFrozenError` exceptions. Note: `assert_ready` is *defined* but not yet *called* — the orchestrator gating is Phase 3.
- [x] **HTTP routes** — ✅ Six new endpoints under `/domains/{id}/task`: `POST` (create), `GET`, `PUT /config`, `POST /freeze`, `POST /unfreeze`, `DELETE`.
- [x] **Tests** — ✅ 9 new tests in [`tests/unit/test_task_service.py`](tests/unit/test_task_service.py): create, freeze/unfreeze, frozen-blocks-config-update, assert_ready missing/unfrozen, persistence round-trip, delete + delete-frozen-raises.

**Done when:** (1a) Two processes (CLI + server) operating on the same `.dojo/` see each other's runs end-to-end; (1b) `Domain` has a Task, the Task has tools, freeze flips a flag, storage survives round-trips. Agent run wiring not touched yet.

---

## Phase 2 — CLI happy path + PROGRAM.md convention

The user-facing surface for everything Phase 1 introduced, plus the framework for the rest of the CLI.

### 2a — Foundations

- [x] **`src/dojo/cli/state.py`** ✅ Manages `.dojo/state.yaml`. Exposes `load_state`, `save_state`, `get_current_domain_id`, `set_current_domain_id`, `set_current_run_id`, plus an async `resolve_domain(lab, base_dir, override=None)` that errors with actionable messages.
- [x] **`src/dojo/cli/_lab.py`** ✅ `build_cli_lab() -> (LabEnvironment, Settings)` — used by every runtime-touching CLI command. No HTTP.
- [x] **`PROGRAM.md` convention codified.** ✅ `runtime/program_loader.py` defines `resolve_program_path`, `load_program`, `write_program`, `default_program_template`. The orchestrator now calls `load_program(domain)` at run start and overrides `domain.prompt` with PROGRAM.md content if present.

### 2b — `dojo init` (the single entrypoint)

A single command that gets a user from "empty directory" to "ready to run" — interactive by default, all-flags for CI.

```bash
# Interactive — wizard walks the user through every step
dojo init

# Non-interactive — for CI, docs, scripts
dojo init \
  --name "California housing" \
  --workspace . \
  --task-type regression \
  --data-path ./data/housing.csv \
  --target-column MedHouseVal \
  --test-split 0.2 \
  --tracking file \
  --no-confirm
```

What `dojo init` does, in order:

1. **Config bootstrap.** Calls existing `config init` if `.dojo/config.yaml` is absent. Asks (or takes flags for) tracking backend (`file` / `mlflow`), memory backend, agent backend (`claude` / `stub`).
2. **Domain creation.** Reuses `_create_domain` flow from [`cli/domain.py`](src/dojo/cli/domain.py). Workspace setup (venv, deps) runs synchronously — surface progress via `rich.progress`.
3. **PROGRAM.md scaffold.** Writes `<workspace>/PROGRAM.md` (or domain-local fallback) with a templated steering prompt that includes the task type and key context. Stores the path on `Domain.program_path`.
4. **Task creation.** Asks (or takes flags for) task type — only `regression` allowed today — plus `data_path`, `target_column`, `test_split_ratio`. Calls `TaskService.create_task`.
5. **Tool generation + verification + freeze.** Phase 3 work; until that lands, this step generates+stores the tools but skips verification and only freezes if `--unsafe-skip-verify` is passed (force the user to acknowledge the gap explicitly).
6. **Sets `current_domain_id`** in `.dojo/state.yaml`.
7. **Prints next steps.** "Edit PROGRAM.md and run `dojo run` when ready."

### 2c — Task and run subcommands

- [x] **`src/dojo/cli/task.py`** ✅ `dojo task` group with `show`, `generate [--hint] [--dry-run]`, `freeze [--unsafe-skip-verify]`, `unfreeze`, `setup`. `verify` is deferred to Phase 3 (placeholder warning in `freeze`). `generate` is registry-aware: regression tasks use `TASK_TYPE_REGISTRY[REGRESSION].generation_prompt_template`; other types fall back to the generic `build_tool_generation_prompt`. Generated tools land on both `domain.task.tools` and `domain.tools` (Phase 3 collapses to task-only).
- [x] **`src/dojo/cli/run.py`** ✅ Rewritten — in-process. Resolves current domain → loads PROGRAM.md → builds orchestrator → streams events to the terminal as they're produced (no HTTP). Persists the run via `lab.run_store` so the server / other CLI invocations see it. Writes `current_run_id` to `state.yaml`. Supports `--domain`, `--max-turns`, `--max-budget-usd`, `--no-watch`, `--prompt`.
- [x] **`src/dojo/cli/runs.py`** ✅ `dojo runs ls` (table or `--json`, `--all`, `--limit`) and `dojo runs show [<id>]` (defaults to `current_run_id`, supports `--events` and `--json`). Reads from `lab.run_store` directly.
- [x] **`src/dojo/cli/program.py`** ✅ `dojo program show` and `dojo program edit` (creates from `default_program_template` if missing, opens `$EDITOR` / `$VISUAL` / `--editor`).

### 2d — Wiring + UX

- [x] **`src/dojo/cli/main.py`** ✅ Registers `init`, `run` as top-level commands and `task`, `runs`, `program`, `domain`, `config` as sub-groups.
- [x] **`dojo domain use <name>` and `dojo domain current`** ✅ added so the "no current domain" error message is actionable.
- [x] **Help text + error messages.** ✅ "No current domain" → suggests `dojo init` or `dojo domain use <name>`. Phase 3 will add "task not frozen → `dojo task setup`".

### Definition of done (Phase 2)

- A new user, in an empty dir, can run `dojo init` (with the right flags) and end up with a domain, a task with stored tools, a `PROGRAM.md`, and `current_domain_id` set.
- `dojo run` against that domain starts an agent run *without a running server* (in-process, calling runtime services).
- `dojo task show`, `dojo runs ls`, `dojo program edit` all work and stay responsive.
- The web frontend still works against the API — the CLI didn't break it.

---

## Phase 3 — Tool verification + anti-cheating run gating

This phase is where the *contract* becomes structurally real. Phase 2 wired up the surface; Phase 3 makes the rules enforced.

### 3a — Tool verification

- [ ] **`src/dojo/runtime/tool_verifier.py`** — new. `async verify(tool: DomainTool, contract: ToolContract, workspace: Workspace) -> VerificationResult`. Builds sample inputs from `contract.params_schema`, executes the tool in `LocalSandbox` against the workspace, parses stdout JSON, validates against `contract.returns_schema`. Returns `{verified, errors, sample_output, duration_ms}`.
- [ ] **Extend `DomainTool`** — add `verification: VerificationResult | None = None` field. Persist with the tool.
- [ ] **`src/dojo/tools/tool_generation.py`** — registry-aware. The prompt template comes from `TASK_TYPE_REGISTRY[task.type].generation_prompt_template`, includes the `ToolContract` (return shape, params), the user's natural-language hint, and the `WorkspaceScanner` summary.
- [ ] **`POST /domains/{id}/tools/generate` and `dojo task generate`** — after generation, immediately run the verifier on each tool. Persist tools with verification status. Return tools with verification details in the response / CLI output.
- [ ] **Freeze gate** — `POST /domains/{id}/task/freeze` (and `dojo task freeze`) reject with status 422 / exit 3 if any required tool's `verification.verified` is False. Surface each error clearly.
- [ ] **Tests** — verifier round-trip (good tool passes, bad tool fails with errors); freeze gate enforces verification; E2E from "generate → verify → freeze" on a small sample regression task.

### 3b — Anti-cheating run gating

- [ ] **`src/dojo/agents/orchestrator.py`** — `start()` checks: `domain.task` exists, `domain.task.frozen is True`, all required tools present + verified. If any fails, raise a clear `TaskNotReadyError` *before* the backend is configured.
- [ ] **`src/dojo/tools/server.py`** — `collect_all_tools(lab, domain)` loads tools from `domain.task.tools` (was `domain.tools`). Only registers `executable=True` tools; non-executable hint-only tools stay as system prompt context.
- [ ] **`src/dojo/agents/prompts.py`** — rewrite `_build_domain_section` and add `_build_task_section`. The system prompt frames the contract: agent owns training code via `run_experiment_code`; `load_data` and `evaluate` are frozen tools the agent must call but cannot modify. The metric returned by `evaluate` is the source of truth; `complete_experiment` records that metric. Include the loaded `PROGRAM.md` content as the steering prompt (per Phase 2 convention).
- [ ] **`src/dojo/api/routers/agent.py`** — `POST /agent/run` requires `domain_id` (no fallback to `generate_id()`). Returns 422 with task status info if the domain isn't ready.
- [ ] **`dojo run`** — surfaces the `TaskNotReadyError` cleanly: tells the user exactly which command to run (`dojo task setup` or similar). Exit code 3.
- [ ] **`src/dojo/tools/experiments.py`** — `complete_experiment` only accepts the metrics dict shape `evaluate` returns (loose validation: keys subset of `task.config["expected_metrics"]`).
- [ ] **Tests** — unit: orchestrator rejects runs against unfrozen / taskless / unverified-tool domains. E2E from CLI: `dojo run` against a domain with no task → exit 3 with helpful message; `dojo run` against a frozen task → run completes; metric in tracking matches what `evaluate` would return on canned predictions.

**Done when:** `dojo run` literally cannot start an agent unless there's a frozen, verified task. The system prompt makes the contract obvious. The recorded metric comes from the frozen evaluator.

---

## Phase 4 — End-to-end on a real RegressionTask, CLI-only

This is the validation gate. Everything is driven from the terminal — no frontend involvement required.

- [ ] **Pick a dataset.** California housing is the obvious starter. Sklearn-bundled is fine — no external download.
- [ ] **Reproduce the full happy path from a clean dir:**
  ```bash
  cd /tmp/dojo-housing
  dojo init --name housing --workspace . --task-type regression \
    --data-path "$(python -c 'from sklearn.datasets import fetch_california_housing; print(fetch_california_housing().filename)')" \
    --target-column MedHouseVal --test-split 0.2 --non-interactive
  $EDITOR PROGRAM.md  # write a focused steering prompt
  dojo run --max-turns 30
  ```
- [ ] **Observe**: every experiment has a metric, the metrics are comparable, the agent's training code varies, the evaluator code does not.
- [ ] **Replay test.** Re-run an experiment's recorded code (`.dojo/artifacts/experiments/{id}/run_*.py`) directly. Metric matches the run's recorded metric. (Reproducibility check.)
- [ ] **Cheating test.** Manually inject training code that computes its own bogus metric and tries to log it directly via `log_metrics`, bypassing `evaluate`. Confirm `complete_experiment` records what `evaluate` returned, not the bogus value. Verify via `dojo runs show <id>`.
- [ ] **Knowledge accumulation test.** Start a *second* `dojo run` on the same domain. Inspect the system prompt actually sent (logged to `.dojo/runs/{id}/system_prompt.txt` — add this if missing). It should include the accumulated knowledge from the first run. The agent should visibly use it (different planning).
- [ ] **No-server test.** Run the full path with no `dojo start` in another terminal — everything should work in-process. (This is the smoking gun that the CLI is a real peer of the API, not an httpx wrapper.)
- [ ] **Cross-process visibility test.** While `dojo run` is in flight from terminal A, run `dojo start` in terminal B and open the frontend (or curl `/agent/runs/{id}`) — the in-flight CLI run is visible, with up-to-date events. (This is the smoking gun for Phase 1a.)

**Done when:** all six points pass. This is the "Dojo actually works" milestone — and it's reproducible from `bash` alone.

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

## Status snapshot (update this as we go)

- [x] Phase 0 — Cleanup
- [x] Phase 1 — Task abstraction lands in core (disk as source of truth + Task/TaskService/RunStore)
- [x] Phase 2 — CLI happy path + PROGRAM.md convention
- [ ] Phase 3 — Tool verification + anti-cheating run gating
- [ ] Phase 4 — End-to-end real RegressionTask via CLI
- [ ] Phase 5 — Reconnaissance
