Great — the key requirement you stated is **the correct one**:

> clearly separate *agent*, *compute*, *storage*, *memory*, *experiment environment*, so the runtime can later swap **local / MLflow / Modal / Postgres / Ray / etc.**

What we want is essentially a **hexagonal architecture (ports & adapters)** for Dojo.ml.

That means:

```
Core (domain logic)
    ↑
Interfaces / Ports
    ↑
Infrastructure Adapters
```

So the **core never knows** whether we run:

* locally
* MLflow tracking
* Postgres backend
* Modal compute
* Ray cluster
* S3 / GCS artifact store

Everything plugs through interfaces.

Below is a **complete interface structure** you can implement directly.

---

# High-Level Architecture

```
dojo/

core/                # pure domain logic
    experiment.py
    hypothesis.py
    state_machine.py

interfaces/          # all abstract interfaces (PORTS)
    agent.py
    compute.py
    storage.py
    artifact_store.py
    experiment_store.py
    memory_store.py
    tool_runtime.py

runtime/             # orchestrates the system
    lab_environment.py
    experiment_service.py

agents/
    claude_agent.py
    rule_agent.py

compute/
    local_compute.py
    modal_compute.py
    ray_compute.py

storage/
    local_experiment_store.py
    postgres_experiment_store.py

artifacts/
    local_artifact_store.py
    s3_artifact_store.py
    mlflow_artifact_store.py

memory/
    local_memory_store.py
    vector_memory_store.py

tools/
    create_experiment.py
    run_experiment.py
    read_results.py
    write_knowledge.py

api/
    server.py
```

---

# Core Domain (Pure Logic)

These files **contain zero infrastructure**.

## Experiment

```python
# core/experiment.py

from dataclasses import dataclass, field
from typing import Dict, Any, Optional
from uuid import uuid4


@dataclass
class Hypothesis:
    description: str
    reasoning: str
    expected_outcome: str


@dataclass
class ExperimentResult:
    metrics: Dict[str, float]
    artifacts_uri: Optional[str] = None


@dataclass
class Experiment:

    problem_name: str
    hypothesis: Hypothesis
    config: Dict[str, Any]

    id: str = field(default_factory=lambda: str(uuid4()))

    state: str = "draft"

    result: Optional[ExperimentResult] = None
```

---

# Interface Layer (THE IMPORTANT PART)

These define **the contracts**.

---

# 1. Agent Interface

This allows:

Claude agent
OpenAI agent
Rule agent
Human operator

to all run the same system.

```python
# interfaces/agent.py

from abc import ABC, abstractmethod


class Agent(ABC):

    @abstractmethod
    async def run(self):
        """Start the autonomous agent loop."""
```

---

# 2. Compute Interface

This separates **execution infrastructure**.

Later:

* Local
* Docker
* Ray
* Modal
* Kubernetes

```python
# interfaces/compute.py

from abc import ABC, abstractmethod
from typing import Callable, Any


class ComputeBackend(ABC):

    @abstractmethod
    def run(self, fn: Callable, *args, **kwargs) -> Any:
        """Execute compute task."""
```

---

# 3. Experiment Store Interface

Stores experiment metadata.

Later options:

* local JSON
* Postgres
* MLflow tracking
* BigQuery

```python
# interfaces/experiment_store.py

from abc import ABC, abstractmethod
from typing import List
from dojo.core.experiment import Experiment


class ExperimentStore(ABC):

    @abstractmethod
    def save(self, experiment: Experiment) -> None:
        pass

    @abstractmethod
    def load(self, experiment_id: str) -> Experiment:
        pass

    @abstractmethod
    def list(self) -> List[Experiment]:
        pass
```

---

# 4. Artifact Store Interface

Model artifacts.

Later:

* local filesystem
* S3
* GCS
* MLflow artifacts

```python
# interfaces/artifact_store.py

from abc import ABC, abstractmethod


class ArtifactStore(ABC):

    @abstractmethod
    def save(self, path: str, data: bytes) -> str:
        """Return artifact URI"""

    @abstractmethod
    def load(self, uri: str) -> bytes:
        pass
```

---

# 5. Knowledge / Memory Interface

Stores learnings.

Later:

* JSON
* Postgres
* Vector DB

```python
# interfaces/memory_store.py

from abc import ABC, abstractmethod
from typing import List, Dict


class MemoryStore(ABC):

    @abstractmethod
    def add(self, atom: Dict):
        pass

    @abstractmethod
    def search(self, query: str) -> List[Dict]:
        pass
```

---

# 6. Tool Runtime Interface

This is **the Claude agent integration layer**.

Claude will call tools through this.

```python
# interfaces/tool_runtime.py

from abc import ABC, abstractmethod


class ToolRuntime(ABC):

    @abstractmethod
    def register_tool(self, name: str, fn):
        pass

    @abstractmethod
    async def start(self):
        pass
```

---

# Lab Environment (Dependency Container)

This is **the central wiring**.

Everything is injected.

```python
# runtime/lab_environment.py

from dojo.interfaces.compute import ComputeBackend
from dojo.interfaces.experiment_store import ExperimentStore
from dojo.interfaces.artifact_store import ArtifactStore
from dojo.interfaces.memory_store import MemoryStore


class LabEnvironment:

    def __init__(
        self,
        compute: ComputeBackend,
        experiment_store: ExperimentStore,
        artifact_store: ArtifactStore,
        memory_store: MemoryStore,
    ):

        self.compute = compute
        self.experiment_store = experiment_store
        self.artifact_store = artifact_store
        self.memory_store = memory_store
```

This single object is what you pass to the agent.

---

# Experiment Service (Core Logic)

This executes experiments **using the environment**.

```python
# runtime/experiment_service.py

from dojo.core.experiment import Experiment


class ExperimentService:

    def __init__(self, lab):
        self.lab = lab

    def create(self, experiment: Experiment):

        self.lab.experiment_store.save(experiment)

        return experiment.id

    def run(self, experiment_id: str):

        exp = self.lab.experiment_store.load(experiment_id)

        result = self.lab.compute.run(
            self._execute_experiment,
            exp,
        )

        exp.result = result

        self.lab.experiment_store.save(exp)

        return exp

    def _execute_experiment(self, experiment):

        # actual ML logic executed by compute backend

        return {"accuracy": 0.92}
```

---

# Local Implementations (First Version)

## Local Compute

```python
# compute/local_compute.py

from dojo.interfaces.compute import ComputeBackend


class LocalCompute(ComputeBackend):

    def run(self, fn, *args, **kwargs):

        return fn(*args, **kwargs)
```

---

## Local Experiment Store

```python
# storage/local_experiment_store.py

import json
from pathlib import Path

from dojo.interfaces.experiment_store import ExperimentStore
from dojo.core.experiment import Experiment


class LocalExperimentStore(ExperimentStore):

    def __init__(self, path="experiments"):

        self.path = Path(path)
        self.path.mkdir(exist_ok=True)

    def save(self, experiment: Experiment):

        with open(self.path / f"{experiment.id}.json", "w") as f:
            json.dump(experiment.__dict__, f)

    def load(self, experiment_id: str):

        with open(self.path / f"{experiment_id}.json") as f:
            data = json.load(f)

        return Experiment(**data)

    def list(self):

        return []
```

---

# Claude Agent Wrapper

The Claude Agent SDK becomes **one implementation of Agent**.

```python
# agents/claude_agent.py

from dojo.interfaces.agent import Agent


class ClaudeResearchAgent(Agent):

    def __init__(self, tool_runtime):

        self.tool_runtime = tool_runtime

    async def run(self):

        await self.tool_runtime.start()
```

Claude then uses tools like:

```
create_experiment
run_experiment
get_results
record_learning
```

---

# What This Architecture Gives You

You can now swap components like this:

### Local Development

```
Agent: Claude
Compute: Local
Experiment Store: JSON
Artifacts: filesystem
Memory: JSON
```

---

### Production

```
Agent: Claude
Compute: Modal
Experiment Store: Postgres
Artifacts: MLflow
Memory: Vector DB
```

---

### Large Scale Research

```
Agent: Claude
Compute: Ray cluster
Experiment Store: Postgres
Artifacts: S3
Memory: Pinecone
```

---

# Why This Structure Is Critical

Without this separation:

* experiments mix with compute
* artifacts mix with metadata
* agent logic mixes with orchestration
* switching infrastructure becomes impossible

With this architecture:

Dojo.ml becomes:

> **an operating system for ML research**

Agents are just **users of the OS**.

---

# The One Missing Piece (Very Important)

To make Claude **actually powerful**, you need **one more interface**:

```
CodeExecutionEnvironment
```

Because the real breakthrough comes when the agent can:

* write code
* run code
* inspect outputs
* modify pipelines

That is what turns it from:

```
experiment runner
```

into

```
autonomous ML researcher
```

---

If you'd like, I can also show the **next critical layer**:

**the Dojo.ml "Scientific Method Engine"**

which forces agents to:

```
hypothesis
→ controlled experiment
→ statistical comparison
→ knowledge extraction
```

Without that, even very strong models like Anthropic's Claude will plateau after ~20 experiments.
