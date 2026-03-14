# Workspace Environments & Code Traceability Plan

> Fixing the two biggest operational problems in Dojo.ml: wasted API calls on boilerplate, and missing code traceability for experiments.

---

## 1. Problem Analysis

### 1.1 Wasted API Calls on Boilerplate

**Symptom**: The agent spends 10–50 API calls per run on infrastructure work before doing any actual ML research.

**What happens today**: When a domain has tools pointing to a custom codebase, the agent receives *semantic descriptors* in its system prompt — tool names, descriptions, and example usage snippets. But the agent has no pre-configured execution environment. So it does this:

```
API call 1:  Bash → git clone https://github.com/user/repo.git /tmp/repo
API call 2:  Bash → ls /tmp/repo
API call 3:  Bash → ls /tmp/repo/src
API call 4:  Read → /tmp/repo/src/data.py
API call 5:  Bash → python -m venv /tmp/repo/.venv
API call 6:  Bash → /tmp/repo/.venv/bin/pip install -r /tmp/repo/requirements.txt
API call 7:  Bash → cd /tmp/repo && python -c "from src.data import load_data; ..."
API call 8:  (fails — wrong import path)
API call 9:  Read → /tmp/repo/setup.py  (trying to understand package structure)
API call 10: Bash → cd /tmp/repo && pip install -e .
...
```

Each of these is a full LLM round-trip. At ~$0.01–0.05 per call, 50 setup calls costs $0.50–2.50 before any research begins. Multiply by hundreds of agent runs and this becomes the dominant cost.

**Root cause**: Domain tools are purely informational. The agent is told *what* tools exist, but has no pre-configured environment to *use* them. The agent's `cwd` is the dojo project root, not the user's project. There's no virtual environment, no installed dependencies, and no reliable import paths.

### 1.2 No Code Traceability

**Symptom**: When reviewing experiment results, there's no way to see exactly what code produced those results.

**What happens today**: The agent uses Claude's built-in `Bash` tool to write Python scripts to temp files and execute them. The code lives in `/tmp/` or wherever the agent decides to put it. When the experiment completes, only the metrics are stored — the code is gone.

```
Agent → Write /tmp/exp_001.py (the training script)
Agent → Bash: python /tmp/exp_001.py
Agent → complete_experiment(metrics={...})
# /tmp/exp_001.py is lost after the run
```

**Root cause**: There's no mechanism connecting "code that was executed" to "experiment that recorded the results." The `Experiment` model stores `result.metrics` and `result.logs`, but not the code. The `Bash` tool is a general-purpose escape hatch — Dojo.ml has no visibility into what it's used for.

---

## 2. Design Principles

1. **Agent API calls = reasoning + ML code + tool calls.** Zero calls should go to environment setup, file exploration, or dependency installation.
2. **Setup is a one-time cost, not per-run.** Environment preparation happens when a domain is created, not when an agent run starts.
3. **Easy user setup.** Provide a directory path and optionally a requirements file. Don't require the user to write Python adapter code.
4. **All experiment code is captured.** Every script the agent runs for an experiment is stored and linked to that experiment.
5. **Build on existing architecture.** Extend `Domain`, `DomainTool`, and the tool system — don't replace them.

---

## 3. Solution: Workspace Environments

### 3.1 Concept

A **Workspace** is a persistent, pre-configured execution environment attached to a domain. It is the answer to "where does the agent's code run?"

Instead of the agent figuring out the environment at runtime (clone → explore → install → hope), the workspace is prepared **once** when the domain is created and reused across all agent runs.

```
Before (per run):               After (one-time setup):
┌──────────────┐                ┌──────────────┐
│  Agent Run   │                │ Domain Setup │ (once)
│  clone repo  │ ← 5+ calls    │  workspace   │
│  ls files    │                │  is prepared │
│  setup venv  │                └──────┬───────┘
│  install deps│                       │
│  fix imports │                ┌──────▼───────┐
│  THEN research│               │  Agent Run   │
└──────────────┘                │  → research  │ ← 0 setup calls
                                │  → code      │
                                │  → results   │
                                └──────────────┘
```

### 3.2 Data Model

```python
class WorkspaceSource(StrEnum):
    LOCAL = "local"         # Existing directory on disk
    GIT = "git"             # Clone from git URL (once)
    EMPTY = "empty"         # Fresh directory (agent works from scratch)

@dataclass
class Workspace:
    """Execution environment for a domain's agent runs."""

    path: str                           # Absolute path to workspace root
    source: WorkspaceSource             # How the workspace was created
    python_path: str | None = None      # Path to Python executable (venv)
    env_vars: dict[str, str]            # Additional env vars for execution
    dependencies_file: str | None       # Path to requirements.txt / pyproject.toml
    setup_script: str | None            # Optional one-time setup script
    ready: bool = False                 # Whether setup has completed

    # Git-specific
    git_url: str | None = None          # Git clone URL (if source=git)
    git_ref: str | None = None          # Branch/tag/commit to check out
```

The `Workspace` is stored as part of the `Domain`:

```python
@dataclass
class Domain:
    # ... existing fields ...
    workspace: Workspace | None = None  # NEW
```

### 3.3 Workspace Setup Flow

When a domain is created with a workspace, the system performs a **one-time setup**:

```
1. Resolve workspace path
   ├── LOCAL: validate path exists, use as-is
   ├── GIT: clone to .dojo/workspaces/{domain_id}/
   └── EMPTY: create .dojo/workspaces/{domain_id}/

2. Detect Python environment
   ├── Found existing venv/conda? → use it
   ├── Found pyproject.toml? → create venv, `uv sync` or `pip install -e .`
   ├── Found requirements.txt? → create venv, `pip install -r`
   └── Nothing? → create bare venv

3. Run setup_script (if provided)
   └── e.g., "download data", "compile extensions", etc.

4. Validate
   ├── Python executable works
   ├── Domain tool example_usage snippets execute successfully
   └── Mark workspace.ready = True
```

### 3.4 How Agent Runs Use the Workspace

When `AgentOrchestrator.start()` is called:

1. The orchestrator reads `domain.workspace`
2. Sets `config.cwd = workspace.path` (agent's working directory)
3. Sets `config.python_path = workspace.python_path` (for code execution)
4. Passes workspace env vars to execution context

The agent's `Bash` tool now runs in the workspace directory with the correct Python. No cloning, no setup, no navigation needed.

### 3.5 User Setup Experience

**Option A: Local directory (simplest)**
```
POST /domains
{
  "name": "Housing Price Prediction",
  "description": "Predict housing prices using the Ames dataset",
  "workspace": {
    "source": "local",
    "path": "/Users/me/projects/housing-ml"
  }
}
```

**Option B: Git repo**
```
POST /domains
{
  "name": "Housing Price Prediction",
  "workspace": {
    "source": "git",
    "git_url": "https://github.com/user/housing-ml.git",
    "git_ref": "main"
  }
}
```

**Option C: CLI wizard**
```bash
$ dojo domain create
  Name: Housing Price Prediction
  Workspace source [local/git/empty]: local
  Path: /Users/me/projects/housing-ml

  ✓ Found pyproject.toml — creating virtual environment...
  ✓ Installed 47 packages
  ✓ Found 3 data files: train.csv, test.csv, sample_submission.csv
  ✓ Detected 2 Python modules: src.data, src.models

  → Suggested domain tools (review with `dojo domain tools`):
    1. load_training_data — Load train.csv as DataFrame
    2. load_test_data — Load test.csv as DataFrame
    3. evaluate_submission — Score predictions against sample format

  Domain created: 01JQXYZ...
```

---

## 4. Solution: Executable Domain Tools

### 4.1 The Problem with Semantic-Only Tools

Current domain tools are text in the system prompt:

```
### Domain-specific tools
- **load_dataset** — Load the housing training data
  Example usage:
  ```python
  import pandas as pd
  df = pd.read_csv("/Users/me/projects/housing-ml/data/train.csv")
  ```
```

The agent reads this, then writes its own code mimicking the example. But if the import path is wrong, the file moved, or the agent is running from a different `cwd`, it fails. The agent then burns API calls debugging.

### 4.2 Two Tiers of Domain Tools

We introduce two tiers:

| Tier | Name | How Agent Uses It | User Effort |
|------|------|-------------------|-------------|
| **Tier 1** | Hint Tool (current) | Text in system prompt, agent writes own code | Low — just name + description |
| **Tier 2** | Executable Tool (new) | Agent calls as MCP tool, gets structured result | Medium — provide implementation code |

**Tier 2 tools are real MCP tools** that the agent calls like `create_experiment` or `write_knowledge`. When the agent calls `load_dataset(split="train")`, the system:

1. Executes the tool's Python code in the workspace context
2. Serializes the result (DataFrame → JSON summary, model → path, etc.)
3. Returns the result to the agent as a tool response

### 4.3 Executable Tool Definition

```python
@dataclass
class DomainTool:
    # ... existing fields ...
    executable: bool = False            # NEW: is this a callable MCP tool?
    code: str = ""                      # NEW: Python function body (for executable tools)
    return_description: str = ""        # NEW: what the tool returns
```

Example executable tool:

```json
{
  "name": "load_training_data",
  "description": "Load the housing training dataset as a pandas DataFrame. Returns a summary of the data (shape, columns, dtypes, head).",
  "type": "data_loader",
  "executable": true,
  "code": "import pandas as pd\ndf = pd.read_csv('data/train.csv')\nresult = {'shape': list(df.shape), 'columns': list(df.columns), 'dtypes': {k: str(v) for k, v in df.dtypes.items()}, 'head': df.head().to_dict()}\nreturn result",
  "parameters": {
    "type": "object",
    "properties": {
      "sample_frac": {
        "type": "number",
        "description": "Fraction of data to sample (default 1.0)"
      }
    }
  },
  "return_description": "Dict with shape, columns, dtypes, and head (first 5 rows)"
}
```

### 4.4 Execution Model

When an executable domain tool is called:

```python
async def execute_domain_tool(tool: DomainTool, args: dict, workspace: Workspace) -> ToolResult:
    """Execute a domain tool in the workspace's Python environment."""

    # 1. Build a Python script that:
    #    - Sets up the function with args
    #    - Executes the tool's code
    #    - Serializes result to JSON on stdout
    script = _build_tool_script(tool.code, args)

    # 2. Run in workspace context
    result = await sandbox.execute(
        script,
        cwd=workspace.path,
        python_path=workspace.python_path,
        env_vars=workspace.env_vars,
    )

    # 3. Parse result
    if result.exit_code == 0:
        return ToolResult(data=json.loads(result.stdout))
    else:
        return ToolResult(error=result.stderr)
```

### 4.5 Auto-Generation of Executable Tools

When a workspace is set up, the system can auto-generate executable tool suggestions:

```
Scan workspace →
  Found data/train.csv (45MB, 81 columns)
  Found data/test.csv (22MB, 80 columns)
  Found src/features.py with function `engineer_features(df)`
  Found src/evaluate.py with function `score_predictions(y_true, y_pred)`

Generated tools:
  1. load_training_data → pd.read_csv("data/train.csv")
  2. load_test_data → pd.read_csv("data/test.csv")
  3. engineer_features → from src.features import engineer_features; ...
  4. score_predictions → from src.evaluate import score_predictions; ...
```

The user reviews and approves these. The AI-assisted generation endpoint (`/domains/{id}/tools/generate`) already exists — we extend it to produce executable tools.

### 4.6 Why This Reduces API Calls

**Before** (semantic tool, 8+ calls):
```
Agent reads system prompt: "load_dataset — Load housing data, example: pd.read_csv(...)"
→ Bash: pip install pandas               (call 1)
→ Write: /tmp/load.py                     (call 2)
→ Bash: python /tmp/load.py              (call 3 — fails, wrong path)
→ Bash: ls data/                          (call 4)
→ Write: /tmp/load2.py (fixed path)       (call 5)
→ Bash: python /tmp/load2.py             (call 6)
→ (reads output, understands data)        (call 7)
→ NOW starts actual ML work              (call 8+)
```

**After** (executable tool, 1 call):
```
Agent calls: load_training_data()         (call 1 — returns data summary)
→ Starts actual ML work                  (call 2+)
```

---

## 5. Solution: `run_experiment_code` Tool (Code Traceability)

### 5.1 Concept

A new MCP tool that replaces raw `Bash` usage for experiment code. It:

1. **Executes code** in the workspace environment (correct cwd, correct Python, correct deps)
2. **Captures the code** and stores it as an experiment artifact
3. **Returns structured results** (stdout, stderr, exit code, execution time)
4. **Links code to experiment** — every script is traceable

### 5.2 Tool Definition

```python
ToolDef(
    name="run_experiment_code",
    description=(
        "Execute Python code for an experiment. The code runs in the domain's "
        "workspace environment with all dependencies available. The code is "
        "automatically saved as an experiment artifact for traceability. "
        "Use this instead of Bash for all experiment code."
    ),
    parameters={
        "type": "object",
        "properties": {
            "experiment_id": {
                "type": "string",
                "description": "The experiment this code belongs to",
            },
            "code": {
                "type": "string",
                "description": "Python code to execute",
            },
            "description": {
                "type": "string",
                "description": "Brief description of what this code does",
            },
        },
        "required": ["experiment_id", "code"],
    },
)
```

### 5.3 Execution Flow

```python
async def run_experiment_code(args: dict) -> ToolResult:
    experiment_id = args["experiment_id"]
    code = args["code"]
    description = args.get("description", "")

    # 1. Validate experiment exists and is RUNNING
    exp = await experiment_store.load(experiment_id)
    if exp is None or exp.state != ExperimentState.RUNNING:
        return ToolResult(error="Experiment not found or not in RUNNING state")

    # 2. Get workspace from domain
    domain = await domain_store.load(exp.domain_id)
    workspace = domain.workspace

    # 3. Save code as artifact BEFORE execution
    run_number = await _next_run_number(experiment_id)
    code_path = f"experiments/{experiment_id}/run_{run_number}.py"
    await artifact_store.save(code_path, code.encode())

    # 4. Execute in workspace context
    result = await sandbox.execute(
        code,
        cwd=workspace.path,
        python_path=workspace.python_path,
        env_vars=workspace.env_vars,
        timeout=workspace.timeout or 300,
    )

    # 5. Save execution metadata as artifact
    meta = {
        "run_number": run_number,
        "code_path": code_path,
        "description": description,
        "exit_code": result.exit_code,
        "duration_ms": result.duration_ms,
        "timestamp": datetime.now(UTC).isoformat(),
    }
    await artifact_store.save(
        f"experiments/{experiment_id}/run_{run_number}_meta.json",
        json.dumps(meta).encode(),
    )

    # 6. Return structured result
    return ToolResult(
        data={
            "exit_code": result.exit_code,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "duration_ms": result.duration_ms,
            "code_path": code_path,
            "run_number": run_number,
        }
    )
```

### 5.4 What Gets Stored

For each `run_experiment_code` call:

```
.dojo/artifacts/experiments/{experiment_id}/
├── run_1.py                # The actual Python code (first execution)
├── run_1_meta.json         # Metadata (exit code, duration, timestamp)
├── run_2.py                # Second execution (e.g., after fixing a bug)
├── run_2_meta.json
└── ...
```

The `Experiment` model is extended:

```python
@dataclass
class ExperimentResult:
    metrics: dict[str, float]
    artifacts: list[str]        # Artifact paths
    logs: list[str]
    error: str | None = None
    code_runs: list[CodeRun]    # NEW: all code executions for this experiment

@dataclass
class CodeRun:
    """Record of a single code execution within an experiment."""
    run_number: int
    code_path: str              # Path to the stored code
    description: str
    exit_code: int
    duration_ms: float
    timestamp: datetime
```

### 5.5 Frontend Integration

On the experiment detail view, add a "Code" tab:

```
Experiment: exp_01JQXYZ
Hypothesis: "LightGBM with tuned hyperparameters outperforms baseline RF"
Status: COMPLETED

[Metrics] [Code] [Logs]

Code Runs:
┌─────┬────────────────────────────┬──────────┬──────────┐
│ Run │ Description                │ Status   │ Duration │
├─────┼────────────────────────────┼──────────┼──────────┤
│  1  │ Training LightGBM model    │ ✓ exit 0 │ 12.3s    │
│  2  │ Hyperparameter tuning      │ ✓ exit 0 │ 45.1s    │
│  3  │ Final evaluation           │ ✓ exit 0 │ 8.7s     │
└─────┴────────────────────────────┴──────────┴──────────┘

▼ Run 2: Hyperparameter tuning
┌─────────────────────────────────────────────────────┐
│ import lightgbm as lgb                              │
│ from sklearn.model_selection import cross_val_score  │
│ ...                                                 │
│ params = {                                          │
│     'n_estimators': 500,                            │
│     'learning_rate': 0.05,                          │
│     'max_depth': 6,                                 │
│ }                                                   │
│ ...                                                 │
└─────────────────────────────────────────────────────┘
```

---

## 6. System Prompt Changes

### 6.1 Updated Prompt Structure

The system prompt is updated to make the agent aware of the workspace and the `run_experiment_code` tool:

```python
def build_system_prompt(run, *, domain, accumulated_knowledge):
    # ... existing preamble ...

    workspace_section = _build_workspace_section(domain)
    tools_section = _build_tools_section(domain)  # now distinguishes hint vs executable

    return f"""You are an autonomous ML research agent operating within Dojo.ml.

## Your role
You systematically explore ML approaches to solve a given problem. You create
experiments, write and execute code, track results, and record learnings.

## Your domain ID
{run.domain_id}
{domain_section}
{workspace_section}
## Available Dojo.ml tools (via MCP)

### Platform tools
- **create_experiment** — Register a new experiment before running code
- **complete_experiment** — Mark as done with metrics
- **fail_experiment** — Mark as failed
- **run_experiment_code** — Execute Python code for an experiment (USE THIS, not Bash)
- **compare_experiments** — Side-by-side metric comparison
- **log_metrics** / **log_params** — Log to tracking backend
- **write_knowledge** / **search_knowledge** / **list_knowledge** — Knowledge management
{tools_section}
## Code execution — IMPORTANT
Use `run_experiment_code` for ALL experiment code. This tool:
- Runs in the workspace with all dependencies pre-installed
- Automatically saves your code as an experiment artifact
- Returns stdout, stderr, and exit code

DO NOT use Bash to:
- Clone repositories (the workspace already has the code)
- Install packages (the workspace has all dependencies)
- Set up virtual environments (already configured)
- Navigate/explore the file tree (domain tools describe what's available)

Only use Bash for quick one-liners unrelated to experiments (checking versions, etc).
{knowledge_section}
## Workflow
1. Search knowledge first
2. Plan your experimental approach
3. For each experiment:
   a. create_experiment with a hypothesis
   b. run_experiment_code with your training/evaluation script
   c. Parse metrics from stdout, then log_metrics + complete_experiment
   d. write_knowledge with what you learned
4. After 2+ experiments, compare_experiments
5. Iterate and summarize
{hints_section}"""
```

### 6.2 New Prompt Sections

```python
def _build_workspace_section(domain: Domain | None) -> str:
    if domain is None or domain.workspace is None:
        return ""

    ws = domain.workspace
    lines = ["\n## Workspace environment"]
    lines.append(f"Your working directory is: `{ws.path}`")
    lines.append("All dependencies are pre-installed. Do not install packages.")
    if ws.python_path:
        lines.append(f"Python: `{ws.python_path}`")
    return "\n".join(lines)


def _build_tools_section(domain: Domain | None) -> str:
    """Build tools section, distinguishing executable vs hint tools."""
    if domain is None or not domain.tools:
        return ""

    executable = [t for t in domain.tools if t.executable]
    hints = [t for t in domain.tools if not t.executable]

    lines = []
    if executable:
        lines.append("\n### Domain tools (callable)")
        lines.append("These are MCP tools you can call directly:\n")
        for tool in executable:
            lines.append(f"- **{tool.name}** — {tool.description}")
            if tool.return_description:
                lines.append(f"  Returns: {tool.return_description}")

    if hints:
        lines.append("\n### Domain reference (for use in your code)")
        for tool in hints:
            lines.append(f"- **{tool.name}** — {tool.description}")
            if tool.example_usage:
                lines.append(f"  Usage:\n```python\n{tool.example_usage}\n```")

    return "\n".join(lines)
```

---

## 7. Sandbox Changes

### 7.1 Enhanced LocalSandbox

The current `LocalSandbox` executes code in a temp directory with no context. We need it to support workspace execution:

```python
class LocalSandbox(Sandbox):
    async def execute(
        self,
        code: str,
        *,
        language: str = "python",
        cwd: str | None = None,          # NEW: working directory
        python_path: str | None = None,   # NEW: specific Python executable
        env_vars: dict[str, str] | None = None,  # NEW: environment variables
        timeout: float | None = None,     # NEW: override default timeout
    ) -> ExecutionResult:
        """Execute code, optionally in a workspace context."""

        effective_timeout = timeout or self.timeout
        effective_python = python_path or "python"

        # Write script to workspace (not temp dir) for traceability
        work_dir = cwd or tempfile.mkdtemp()
        script_path = Path(work_dir) / f"_dojo_run_{uuid4().hex[:8]}.py"
        script_path.write_text(code)

        env = {**os.environ, **(env_vars or {})}

        try:
            proc = await asyncio.create_subprocess_exec(
                effective_python,
                str(script_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=work_dir,
                env=env,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=effective_timeout,
            )
            # ... return result
        finally:
            # Clean up the temp script (artifact is stored separately)
            script_path.unlink(missing_ok=True)
```

---

## 8. API Changes

### 8.1 Domain Endpoints (modified)

**Create domain** now accepts workspace config:

```
POST /domains
{
  "name": "Housing Price Prediction",
  "description": "...",
  "prompt": "Focus on feature engineering and gradient boosting methods.",
  "workspace": {
    "source": "local",
    "path": "/Users/me/projects/housing-ml"
  }
}
```

**Response** includes workspace status:

```json
{
  "id": "01JQXYZ...",
  "name": "Housing Price Prediction",
  "workspace": {
    "path": "/Users/me/projects/housing-ml",
    "source": "local",
    "ready": false
  }
}
```

### 8.2 Workspace Endpoints (new)

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/domains/{id}/workspace/setup` | Trigger workspace setup (venv, deps) |
| `GET` | `/domains/{id}/workspace/status` | Check setup progress |
| `POST` | `/domains/{id}/workspace/validate` | Validate workspace (run tool examples) |

### 8.3 Experiment Code Endpoints (new)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/experiments/{id}/code` | List all code runs for an experiment |
| `GET` | `/experiments/{id}/code/{run_number}` | Get specific code run (code + metadata) |

---

## 9. Implementation Plan

### Phase 1: Workspace Foundation

**Goal**: Domains have workspaces. Agent runs use the workspace as cwd. No more cloning/setup in agent loops.

1. Add `Workspace` and `WorkspaceSource` to `core/domain.py`
2. Add `CodeRun` to `core/experiment.py`
3. Extend `LocalDomainStore` to persist workspace config
4. Create `WorkspaceService` in `runtime/`:
   - `setup_workspace(domain)` — detect env, create venv, install deps
   - `validate_workspace(domain)` — run tool examples, check Python works
   - `get_status(domain_id)` — return setup progress
5. Update `AgentOrchestrator.start()` to set `cwd` and `python_path` from workspace
6. Add workspace fields to domain API request/response schemas
7. Add `/domains/{id}/workspace/*` endpoints
8. Update `build_system_prompt` to include workspace section
9. Tests: workspace setup for local dir, git repo, empty workspace

### Phase 2: `run_experiment_code` Tool

**Goal**: Agent uses `run_experiment_code` instead of Bash for experiments. All code is captured.

1. Extend `Sandbox` interface with `cwd`, `python_path`, `env_vars` parameters
2. Update `LocalSandbox` to support workspace execution context
3. Create `run_experiment_code` tool in `tools/experiments.py`
4. Add code artifact storage logic (save script + metadata)
5. Extend `ExperimentResult` with `code_runs: list[CodeRun]`
6. Update `ExperimentService` to track code runs
7. Add `/experiments/{id}/code` API endpoints
8. Update system prompt to instruct agent to use `run_experiment_code`
9. Tests: code execution in workspace, artifact storage, traceability

### Phase 3: Executable Domain Tools

**Goal**: Domain tools can be actual callable MCP tools, not just system prompt text.

1. Add `executable`, `code`, `return_description` fields to `DomainTool`
2. Create `DomainToolExecutor` in `tools/domain_tools.py`:
   - Wraps tool code as a sandboxed Python function
   - Registers as MCP `ToolDef` with JSON-serialized results
3. Update `collect_all_tools()` to include executable domain tools
4. Update `_build_tools_section()` in prompts to distinguish tiers
5. Extend tool generation endpoint to produce executable tools
6. Add tool validation — run tool code in workspace to verify it works
7. Tests: executable tool registration, execution, result serialization

### Phase 4: Auto-Setup & CLI

**Goal**: Make workspace setup as easy as possible for users.

1. Create `WorkspaceScanner` — auto-detect project structure:
   - Find data files (CSV, parquet, JSON)
   - Find Python modules and their public functions
   - Find dependency files (pyproject.toml, requirements.txt)
   - Detect common ML frameworks (sklearn, torch, lightgbm, etc.)
2. Auto-generate executable tool suggestions from scan results
3. `dojo domain create` CLI command with interactive wizard
4. `dojo domain scan` CLI command to re-scan and suggest tools
5. Frontend: workspace setup status indicator on domain page
6. Frontend: code viewer in experiment detail view

---

## 10. Migration & Backward Compatibility

### Existing Domains

Domains without a workspace continue to work exactly as they do today. The workspace field is optional (`workspace: Workspace | None = None`). If no workspace is configured:

- Agent runs use the current default `cwd` (dojo project root or configured path)
- Domain tools remain semantic hints in the system prompt
- `run_experiment_code` still works but executes with default Python in default cwd

### Gradual Adoption

Users can add workspaces to existing domains at any time:
```
PUT /domains/{id}
{ "workspace": { "source": "local", "path": "/my/project" } }
POST /domains/{id}/workspace/setup
```

### Tool Backward Compatibility

The `executable` field defaults to `false`. Existing domain tools remain hint-only unless explicitly upgraded to executable.

---

## 11. Expected Impact

### API Call Reduction

| Scenario | Before | After | Savings |
|----------|--------|-------|---------|
| Setup (clone + env) | 10-30 calls | 0 calls | 100% |
| Data loading (semantic tool) | 3-8 calls | 1 call | 62-87% |
| Code execution (Bash) | 2-4 calls per script | 1 call | 50-75% |
| **Typical run (5 experiments)** | **40-80 calls** | **15-25 calls** | **~60%** |

### Cost Reduction

At ~$0.03 per API call average:
- Before: 60 calls × $0.03 = $1.80 per run
- After: 20 calls × $0.03 = $0.60 per run
- **~67% cost reduction per agent run**

### Code Traceability

- Before: 0% of experiment code is captured
- After: 100% of experiment code is captured and linked to experiments
- Every experiment result can be reproduced by re-running its stored code

---

## 12. Summary

| Problem | Solution | Key Change |
|---------|----------|------------|
| Agent wastes calls on env setup | **Workspace Environments** | One-time setup, not per-run |
| Agent wastes calls exploring files | **Executable Domain Tools** | Call tool directly, get data back |
| Agent wastes calls on imports/paths | **Workspace cwd + python_path** | Correct context from the start |
| No code traceability | **`run_experiment_code` tool** | Code captured as experiment artifact |
| Hard user setup | **Auto-scan + CLI wizard** | Detect project structure, suggest tools |

The three solutions work together:
1. **Workspace** eliminates environment setup calls
2. **Executable tools** eliminate data loading / exploration calls
3. **`run_experiment_code`** eliminates Bash overhead while adding traceability

Total estimated API call reduction: **~60%**, with full code traceability as a bonus.
