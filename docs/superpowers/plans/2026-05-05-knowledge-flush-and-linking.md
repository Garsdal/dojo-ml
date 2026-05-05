# Knowledge Flush + Stop UX + Atom/Link Logging Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop runs produce few high-quality knowledge atoms, the user sees the flush is happening, logs distinguish atom-create from link-create, and SSE consumers receive the new events.

**Architecture:** No new abstractions. Reuse `AgentEvent.event_type` (already a free-form string) for two new flush events that flow through the existing `run.events` list to both CLI and SSE consumers. Tighten the flush prompt and add a confidence floor at the parse site. Split the single misleading `knowledge_linked` log line into two events. Add a `run_finalized` event so SSE waits for the post-status flush instead of terminating early.

**Tech Stack:** Python 3.13, structlog, FastAPI + sse-starlette, pytest (`asyncio_mode=auto`), Typer, Rich.

**Spec:** [docs/superpowers/specs/2026-05-05-knowledge-flush-and-linking-design.md](../specs/2026-05-05-knowledge-flush-and-linking-design.md)

---

## File Structure

| File | Role | Change |
|---|---|---|
| `src/dojo/runtime/knowledge_linker.py` | DEAD CODE — orphaned near-duplicate of `keyword_linker.py`, no imports anywhere | Delete |
| `src/dojo/runtime/keyword_linker.py` | The wired-in keyword overlap linker | Split `knowledge_linked` into `knowledge_atom_created` + `knowledge_link_created` |
| `src/dojo/agents/summarizer.py` | End-of-run knowledge extraction | Tighter prompt, confidence floor, emit flush start/completed events |
| `src/dojo/agents/orchestrator.py` | Run lifecycle | Pass `run.events` through to `flush_run_knowledge`; emit `run_finalized` at end of `execute()` |
| `src/dojo/api/routers/agent.py` | SSE event stream | Terminate on `run_finalized` instead of `run.status` |
| `src/dojo/cli/run.py` | Terminal UX | Render new event types; drop redundant inline prints from `_graceful_stop` |
| `tests/unit/test_knowledge_linker.py` | Linker unit tests | Update for new event names |
| `tests/unit/test_summarizer.py` | NEW | Confidence filter, prompt cap, flush-event emission |
| `tests/unit/test_orchestrator.py` | Orchestrator unit tests | Add `run_finalized` test |
| `tests/integration/test_memory_integration.py` | Memory + orchestrator integration | Adjust to assert new events appear (or skip if log-only) |

Each file has one clear responsibility; nothing crosses concerns. The orchestrator stays SDK-agnostic (it only knows about events). The CLI stays presentation-only. The summarizer owns "what counts as a durable finding" and the flush event lifecycle. The linker owns "create atom + write links."

---

## Task 1: Delete dead `runtime/knowledge_linker.py`

**Files:**
- Delete: `src/dojo/runtime/knowledge_linker.py`

The file is an orphaned near-duplicate of `keyword_linker.py` (different `LinkingResult` definition, no interface implementation). Confirmed via grep: nothing imports it. Removing it now prevents future drift while we change log event names in the live linker.

- [ ] **Step 1: Confirm nothing imports the file**

Run:
```bash
grep -rn "from dojo.runtime.knowledge_linker\|import dojo.runtime.knowledge_linker" src tests | grep -v __pycache__
```
Expected: empty output.

- [ ] **Step 2: Delete the file**

```bash
rm src/dojo/runtime/knowledge_linker.py
```

- [ ] **Step 3: Run tests + lint**

```bash
just test && just lint
```
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "chore(runtime): drop orphaned knowledge_linker.py duplicate"
```

---

## Task 2: Split `knowledge_linked` into `knowledge_atom_created` + `knowledge_link_created`

**Files:**
- Modify: `src/dojo/runtime/keyword_linker.py:97-102`
- Test: `tests/unit/test_knowledge_linker.py` (add new test)

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_knowledge_linker.py`:

```python
import logging


async def test_emits_atom_created_and_link_created_events(
    linker: KeywordKnowledgeLinker, caplog
):
    """produce_knowledge emits one knowledge_atom_created event always,
    and one knowledge_link_created per link written."""
    caplog.set_level(logging.INFO, logger="dojo.runtime.keyword_linker")

    # First atom — no prior atoms so only CREATED_BY link.
    await linker.produce_knowledge(
        context="ctx-A",
        claim="claim about gradient boosting on tabular data",
        experiment_id="exp-1",
        domain_id="dom-1",
    )

    events = [r.msg for r in caplog.records]
    assert "knowledge_atom_created" in events
    # CREATED_BY is the only link for the first atom.
    assert events.count("knowledge_link_created") == 1
    # Old aggregate event is gone.
    assert "knowledge_linked" not in events


async def test_link_created_event_per_related_link(
    linker: KeywordKnowledgeLinker, caplog
):
    """A second similar atom triggers an additional knowledge_link_created
    event for the RELATED_TO link."""
    caplog.set_level(logging.INFO, logger="dojo.runtime.keyword_linker")

    await linker.produce_knowledge(
        context="housing price prediction with gradient boosting",
        claim="random forests outperform linear regression on tabular housing data",
        experiment_id="exp-1",
        domain_id="dom-1",
    )
    caplog.clear()

    await linker.produce_knowledge(
        context="extended housing price prediction with cross-validation",
        claim="random forests outperform linear regression on tabular housing data again",
        experiment_id="exp-2",
        domain_id="dom-1",
    )

    events = [r.msg for r in caplog.records]
    assert events.count("knowledge_atom_created") == 1
    # CREATED_BY + 1 RELATED_TO = 2 link events.
    assert events.count("knowledge_link_created") == 2
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run:
```bash
uv run pytest tests/unit/test_knowledge_linker.py::test_emits_atom_created_and_link_created_events tests/unit/test_knowledge_linker.py::test_link_created_event_per_related_link -v
```
Expected: FAIL — tests assert events that don't exist yet (`knowledge_atom_created`, `knowledge_link_created`).

- [ ] **Step 3: Update `keyword_linker.py` to emit split events**

Replace [src/dojo/runtime/keyword_linker.py:69-102](../../src/dojo/runtime/keyword_linker.py#L69-L102) with:

```python
        atom = KnowledgeAtom(
            context=context,
            claim=claim,
            action=action,
            confidence=confidence,
            evidence_ids=evidence,
            version=1,
        )
        await self._memory.add(atom)
        logger.info(
            "knowledge_atom_created",
            atom_id=atom.id,
            domain_id=domain_id,
            experiment_id=experiment_id,
            confidence=confidence,
        )

        # 2. Find similar existing atoms (for grouping, not merging)
        similar = await self.find_similar(context, claim, exclude_id=atom.id)

        # 3. Create CREATED_BY link from this atom to the experiment/domain
        if experiment_id or domain_id:
            link = KnowledgeLink(
                atom_id=atom.id,
                experiment_id=experiment_id or "",
                domain_id=domain_id,
                link_type=LinkType.CREATED_BY,
            )
            await self._links.link(link)
            logger.info(
                "knowledge_link_created",
                atom_id=atom.id,
                link_type=LinkType.CREATED_BY.value,
                domain_id=domain_id,
                experiment_id=experiment_id,
            )

        # 4. Create RELATED_TO links to similar atoms
        related_ids: list[str] = []
        for existing in similar:
            rel_link = KnowledgeLink(
                atom_id=atom.id,
                experiment_id=experiment_id or "",
                domain_id=domain_id,
                link_type=LinkType.RELATED_TO,
                related_atom_id=existing.id,
            )
            await self._links.link(rel_link)
            logger.info(
                "knowledge_link_created",
                atom_id=atom.id,
                link_type=LinkType.RELATED_TO.value,
                related_atom_id=existing.id,
                domain_id=domain_id,
                experiment_id=experiment_id,
            )
            related_ids.append(existing.id)
```

(The single `logger.info("knowledge_linked", ...)` block at the bottom is removed entirely.)

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/unit/test_knowledge_linker.py -v
```
Expected: all tests in file PASS.

- [ ] **Step 5: Commit**

```bash
git add src/dojo/runtime/keyword_linker.py tests/unit/test_knowledge_linker.py
git commit -m "feat(linker): split knowledge_linked log into atom_created + link_created"
```

---

## Task 3: Tighten flush prompt + confidence floor

**Files:**
- Modify: `src/dojo/agents/summarizer.py:33-77`
- Create: `tests/unit/test_summarizer.py`

- [ ] **Step 1: Create `tests/unit/test_summarizer.py` with the failing tests**

```python
"""Unit tests for end-of-run knowledge flush."""

from __future__ import annotations

import json

import pytest

from dojo.agents.backend import AgentBackend
from dojo.agents.summarizer import extract_knowledge_atoms
from dojo.agents.types import AgentEvent


class _FakeBackend(AgentBackend):
    """Test double whose `complete` returns whatever JSON we ask for."""

    name = "fake"

    def __init__(self, response: str) -> None:
        self._response = response

    async def configure(self, tools, config) -> None:  # pragma: no cover - unused
        pass

    async def execute(self, prompt: str):  # pragma: no cover - unused
        if False:
            yield  # type: ignore[unreachable]

    async def stop(self) -> None:  # pragma: no cover - unused
        pass

    async def complete(self, prompt: str) -> str:
        return self._response


async def test_low_confidence_atoms_dropped():
    """Atoms with confidence < 0.5 must not survive parsing."""
    backend = _FakeBackend(
        json.dumps(
            [
                {"claim": "high signal lesson", "confidence": 0.8},
                {"claim": "weak hunch", "confidence": 0.3},
                {"claim": "borderline", "confidence": 0.49},
            ]
        )
    )
    atoms = await extract_knowledge_atoms(backend, transcript="x", domain_id="d")
    assert [a["claim"] for a in atoms] == ["high signal lesson"]


async def test_atoms_without_explicit_confidence_kept():
    """If the model omits confidence, default 0.5 keeps the atom (the floor is < 0.5, not <= 0.5)."""
    backend = _FakeBackend(json.dumps([{"claim": "no-confidence atom"}]))
    atoms = await extract_knowledge_atoms(backend, transcript="x", domain_id="d")
    assert len(atoms) == 1


async def test_prompt_rejects_dataset_shape_examples():
    """The prompt must explicitly tell the model not to emit dataset-shape facts."""
    captured: dict[str, str] = {}

    class _Capture(_FakeBackend):
        async def complete(self, prompt: str) -> str:
            captured["prompt"] = prompt
            return "[]"

    backend = _Capture("[]")
    await extract_knowledge_atoms(backend, transcript="x", domain_id="d")
    assert "dataset shape" in captured["prompt"].lower()
    assert "transferable" in captured["prompt"].lower()
    # Cap is part of the prompt the model sees.
    assert "3" in captured["prompt"] and "5" in captured["prompt"]


async def test_more_than_five_atoms_truncated():
    """Backstop: if the model returns more than 5 atoms, we keep at most 5."""
    backend = _FakeBackend(
        json.dumps(
            [{"claim": f"finding {i}", "confidence": 0.8} for i in range(10)]
        )
    )
    atoms = await extract_knowledge_atoms(backend, transcript="x", domain_id="d")
    assert len(atoms) <= 5
```

- [ ] **Step 2: Run the new tests to verify they fail**

```bash
uv run pytest tests/unit/test_summarizer.py -v
```
Expected: FAIL — current prompt does not contain the required strings, current parse keeps low-confidence atoms, current parse does not truncate.

- [ ] **Step 3: Rewrite the prompt and add the filters**

Replace [src/dojo/agents/summarizer.py:33-77](../../src/dojo/agents/summarizer.py#L33-L77) with:

```python
# Atoms with confidence below this floor are discarded as a backstop against
# over-confident defaults. The prompt asks the model to calibrate, but we don't
# trust calibration alone.
_CONFIDENCE_FLOOR = 0.5

# Hard cap on flush output. The prompt asks for 3-5; this stops the model from
# returning a larger list when it disregards the instruction.
_MAX_ATOMS = 5


async def extract_knowledge_atoms(
    backend: AgentBackend, transcript: str, domain_id: str
) -> list[dict]:
    """One-shot LLM call asking for durable findings, returned as a JSON list.

    Returns [] when the backend can't do completions (e.g. the stub) or the
    response can't be parsed. Filters out atoms below the confidence floor and
    caps the output length.
    """
    prompt = (
        "You are reviewing the transcript of an autonomous ML research agent. "
        f"Extract only TRANSFERABLE findings that future runs of domain "
        f"{domain_id} (or related domains) would benefit from knowing. "
        "Aim for 3-5 atoms maximum — pick the highest-signal lessons.\n\n"
        "INCLUDE:\n"
        "- Modeling lessons that generalise (e.g. 'tree models beat linear on this dataset shape')\n"
        "- Dead-ends worth avoiding (e.g. 'quadratic feature engineering hurt HistGBM')\n"
        "- Environment gotchas (e.g. 'lightgbm is not installed in this workspace')\n"
        "- Anti-patterns (e.g. 'dropping NaNs before split caused leakage')\n\n"
        "REJECT:\n"
        "- Dataset shape descriptions (row count, column count, column names, schema)\n"
        "- Single-experiment hyperparameter values ('tried n_estimators=1000')\n"
        "- Running totals or progress recaps\n"
        "- Single-experiment numeric results without comparison context\n\n"
        "Calibrate confidence: ≥0.7 = 'I'd bet on this in the next run'. "
        "≤0.3 = 'weak signal, only worth recording if novel'.\n\n"
        "Output ONLY a JSON array (possibly empty) of objects with keys:\n"
        '- "claim": one-sentence finding (required)\n'
        '- "context": short phrase, e.g. "early baseline runs" (optional)\n'
        '- "confidence": float 0.0-1.0 calibrated to evidence (optional, default 0.5)\n'
        '- "experiment_id": ULID if known from transcript (optional)\n\n'
        "If nothing is durable, output [].\n\n"
        "Transcript:\n"
        f"{transcript[:8000]}\n"
    )

    try:
        raw = await backend.complete(prompt)
    except NotImplementedError:
        return []

    raw = raw.strip()
    if raw.startswith("```"):
        lines = [line for line in raw.split("\n") if not line.startswith("```")]
        raw = "\n".join(lines).strip()

    try:
        atoms = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(atoms, list):
        return []

    cleaned: list[dict] = []
    for a in atoms:
        if not isinstance(a, dict) or not a.get("claim"):
            continue
        confidence = float(a.get("confidence", 0.5))
        if confidence < _CONFIDENCE_FLOOR:
            continue
        cleaned.append(a)
    return cleaned[:_MAX_ATOMS]
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/unit/test_summarizer.py -v
```
Expected: all 4 tests PASS.

- [ ] **Step 5: Run full unit suite to catch regressions**

```bash
uv run pytest tests/unit/ -v
```
Expected: no new failures.

- [ ] **Step 6: Commit**

```bash
git add src/dojo/agents/summarizer.py tests/unit/test_summarizer.py
git commit -m "feat(summarizer): demand transferable findings, cap at 5, drop low-confidence atoms"
```

---

## Task 4: Emit `knowledge_flush_started` / `knowledge_flush_completed` events

**Files:**
- Modify: `src/dojo/agents/summarizer.py` (signature of `flush_run_knowledge`)
- Modify: `src/dojo/agents/orchestrator.py:240-256` (pass `run.events`)
- Test: `tests/unit/test_summarizer.py` (extend)

The new events ride on the existing `AgentEvent.event_type` free-form string — no taxonomy change. They land in `run.events`, the same list the CLI polls and SSE reads.

- [ ] **Step 1: Add the failing test**

Append to `tests/unit/test_summarizer.py`:

```python
from dojo.agents.summarizer import flush_run_knowledge


class _LabStub:
    """Minimal lab stub exposing only what flush_run_knowledge touches."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

        class _Linker:
            async def produce_knowledge(_self, **kwargs):
                self.calls.append(kwargs)
                return None

        self.knowledge_linker = _Linker()


async def test_flush_emits_start_and_completed_events_on_success():
    backend = _FakeBackend(
        json.dumps([{"claim": "good lesson", "confidence": 0.8}])
    )
    events: list[AgentEvent] = [
        AgentEvent(event_type="text", data={"text": "transcript content"})
    ]
    lab = _LabStub()

    written = await flush_run_knowledge(
        backend, lab, events=events, domain_id="d", run_id="r"
    )

    types = [e.event_type for e in events]
    assert "knowledge_flush_started" in types
    assert "knowledge_flush_completed" in types
    completed = next(e for e in events if e.event_type == "knowledge_flush_completed")
    assert completed.data == {"count": written}
    assert written == 1


async def test_flush_emits_completed_with_error_on_extract_failure():
    class _Boom(_FakeBackend):
        async def complete(self, prompt: str) -> str:
            raise RuntimeError("model unavailable")

    backend = _Boom("")
    events: list[AgentEvent] = [
        AgentEvent(event_type="text", data={"text": "transcript content"})
    ]
    lab = _LabStub()

    written = await flush_run_knowledge(
        backend, lab, events=events, domain_id="d", run_id="r"
    )
    assert written == 0
    completed = next(e for e in events if e.event_type == "knowledge_flush_completed")
    assert "error" in completed.data
    assert "model unavailable" in completed.data["error"]


async def test_flush_emits_no_events_when_transcript_empty():
    """An empty transcript skips the flush entirely — no user-visible events."""
    backend = _FakeBackend("[]")
    events: list[AgentEvent] = []  # empty transcript
    lab = _LabStub()

    written = await flush_run_knowledge(
        backend, lab, events=events, domain_id="d", run_id="r"
    )
    assert written == 0
    assert events == []  # untouched
```

- [ ] **Step 2: Run the new tests to verify they fail**

```bash
uv run pytest tests/unit/test_summarizer.py -v
```
Expected: the three new tests FAIL — `flush_run_knowledge` doesn't yet append events.

- [ ] **Step 3: Update `flush_run_knowledge` to emit events**

Replace [src/dojo/agents/summarizer.py:80-122](../../src/dojo/agents/summarizer.py#L80-L122) with:

```python
async def flush_run_knowledge(
    backend: AgentBackend,
    lab: LabEnvironment,
    *,
    events: list[AgentEvent],
    domain_id: str,
    run_id: str,
    context_label: str = "end-of-run flush",
) -> int:
    """Extract durable findings from a finished run and persist them as atoms.

    Appends ``knowledge_flush_started`` and ``knowledge_flush_completed`` events
    to the provided ``events`` list so CLI / SSE consumers can render progress.

    Returns the number of atoms written. Safe to call when the backend can't
    do completions (e.g. the stub) — returns 0 instead of raising.
    """
    transcript = collect_transcript(events)
    if not transcript.strip():
        return 0

    events.append(AgentEvent(event_type="knowledge_flush_started", data={}))

    try:
        atoms = await extract_knowledge_atoms(backend, transcript, domain_id)
    except Exception as e:
        logger.warning("knowledge_flush_extract_failed", run_id=run_id, error=str(e))
        events.append(
            AgentEvent(event_type="knowledge_flush_completed", data={"error": str(e)})
        )
        return 0

    written = 0
    for atom in atoms:
        try:
            await lab.knowledge_linker.produce_knowledge(
                context=atom.get("context") or context_label,
                claim=atom["claim"],
                action=atom.get("action", ""),
                confidence=float(atom.get("confidence", 0.5)),
                evidence_ids=atom.get("evidence_ids") or [],
                experiment_id=atom.get("experiment_id", ""),
                domain_id=domain_id,
            )
            written += 1
        except Exception as e:
            logger.warning("knowledge_flush_atom_write_failed", run_id=run_id, error=str(e))

    events.append(
        AgentEvent(event_type="knowledge_flush_completed", data={"count": written})
    )
    if written:
        logger.info("knowledge_flushed", run_id=run_id, atoms=written)
    return written
```

- [ ] **Step 4: Wire the orchestrator to pass `run.events`**

The orchestrator already calls `flush_run_knowledge` from [src/dojo/agents/orchestrator.py:240-256](../../src/dojo/agents/orchestrator.py#L240-L256). It already passes `events=run.events` (verify at the call site):

```python
        return await flush_run_knowledge(
            self.backend,
            self.lab,
            events=run.events,
            domain_id=run.domain_id,
            run_id=run.id,
        )
```

If the existing call already names `events=run.events`, no change needed. If the call site uses a different name or shape, update it to match the signature above. Confirm by grep:

```bash
grep -A 7 "flush_run_knowledge" src/dojo/agents/orchestrator.py
```

- [ ] **Step 5: Run the new tests to verify they pass**

```bash
uv run pytest tests/unit/test_summarizer.py -v
```
Expected: all summarizer tests PASS.

- [ ] **Step 6: Run full unit + integration suite**

```bash
uv run pytest tests/unit/ tests/integration/ -v
```
Expected: no regressions. (Existing memory integration tests don't assert on flush events; they test memory writes, which are unchanged.)

- [ ] **Step 7: Commit**

```bash
git add src/dojo/agents/summarizer.py tests/unit/test_summarizer.py
git commit -m "feat(summarizer): emit knowledge_flush_started/completed events in run.events"
```

---

## Task 5: Emit `run_finalized` event so SSE waits past the flush

**Files:**
- Modify: `src/dojo/agents/orchestrator.py:229-238` (finally block)
- Modify: `src/dojo/api/routers/agent.py:169-196` (SSE termination)
- Test: `tests/unit/test_orchestrator.py` (extend)

**Why:** the SSE generator at [src/dojo/api/routers/agent.py:190-191](../../src/dojo/api/routers/agent.py#L190-L191) terminates as soon as `run.status` is terminal — but the orchestrator runs `flush_knowledge` *after* the status flips, in the `finally` block. So flush events emitted in Task 4 would never reach SSE clients today. Add a sentinel event the SSE generator waits for.

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_orchestrator.py`:

```python
async def test_execute_emits_run_finalized_as_last_event(lab):
    """run.events ends with a run_finalized sentinel after flush completes."""
    backend = StubAgentBackend()
    orchestrator = AgentOrchestrator(lab, backend)

    run = await orchestrator.start("test", domain_id="d", require_ready_task=False)
    await orchestrator.execute(run)

    assert run.events, "expected at least one event"
    assert run.events[-1].event_type == "run_finalized"
```

- [ ] **Step 2: Run to verify it fails**

```bash
uv run pytest tests/unit/test_orchestrator.py::test_execute_emits_run_finalized_as_last_event -v
```
Expected: FAIL — no such event today.

- [ ] **Step 3: Emit the sentinel from `execute()`'s finally block**

In `src/dojo/agents/orchestrator.py`, locate the `finally` block at the end of `execute()` (around [orchestrator.py:229-238](../../src/dojo/agents/orchestrator.py#L229-L238)). After the `flush_knowledge(run)` call, append the sentinel:

```python
        finally:
            stop_watcher.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await stop_watcher
            with contextlib.suppress(Exception):
                await self.lab.run_store.clear_stop_request(run.id)
            # Best-effort: extract durable findings now that the run is done.
            # Idempotent — the CLI graceful-stop path may already have flushed.
            with contextlib.suppress(Exception):
                await self.flush_knowledge(run)
            # Sentinel: SSE consumers wait for this before sending `done`,
            # so the flush events written above reach the frontend.
            run.events.append(AgentEvent(event_type="run_finalized", data={}))
            with contextlib.suppress(Exception):
                await self.lab.run_store.save(run)
```

(`AgentEvent` is already imported at the top of the file.)

- [ ] **Step 4: Run the orchestrator test to verify it passes**

```bash
uv run pytest tests/unit/test_orchestrator.py::test_execute_emits_run_finalized_as_last_event -v
```
Expected: PASS.

- [ ] **Step 5: Update SSE generator to terminate on the sentinel**

In `src/dojo/api/routers/agent.py`, replace the `event_generator()` body inside `stream_events` (around [agent.py:169-194](../../src/dojo/api/routers/agent.py#L169-L194)) with:

```python
    async def event_generator():
        seen = 0
        finalized = False
        while True:
            # Yield new events
            while seen < len(run.events):
                event = run.events[seen]
                seen += 1
                yield {
                    "event": event.event_type,
                    "data": json.dumps(
                        {
                            "id": event.id,
                            "timestamp": event.timestamp.isoformat(),
                            "event_type": event.event_type,
                            "data": event.data,
                        },
                        default=str,
                    ),
                }
                if event.event_type == "run_finalized":
                    finalized = True

            if finalized:
                yield {"event": "done", "data": json.dumps({"status": run.status.value})}
                return

            # Belt-and-braces: if the orchestrator died before emitting
            # run_finalized but the run is in a terminal state with no new
            # events for a while, exit anyway. The orchestrator's finally
            # block is best-effort and a hard crash could skip it.
            if run.status in (RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.STOPPED):
                # Wait one more poll cycle to let any final events land.
                await asyncio.sleep(0.3)
                if seen >= len(run.events):
                    yield {
                        "event": "done",
                        "data": json.dumps({"status": run.status.value}),
                    }
                    return
                continue

            await asyncio.sleep(0.3)
```

- [ ] **Step 6: Run integration tests for agent SSE**

```bash
uv run pytest tests/integration/ tests/e2e/ -v
```
Expected: no regressions. SSE consumers still receive `done` after terminal status; flush events now appear before `done` when present.

- [ ] **Step 7: Commit**

```bash
git add src/dojo/agents/orchestrator.py src/dojo/api/routers/agent.py tests/unit/test_orchestrator.py
git commit -m "feat(orchestrator,api): emit run_finalized so SSE waits for flush events"
```

---

## Task 6: Render new events in CLI; drop redundant `_graceful_stop` prints

**Files:**
- Modify: `src/dojo/cli/run.py:217-241` (`_print_event`)
- Modify: `src/dojo/cli/run.py:246-283` (`_graceful_stop`)

The CLI's `_stream_events` already polls `run.events` until `execute_task.done()`. Because the orchestrator's flush + `run_finalized` happen *inside* `execute()`, those events naturally appear before the task completes. We just need to render them.

The SIGINT handler keeps printing the "stop requested — finishing up (Ctrl-C again to abort cleanup)" hint. `_graceful_stop` no longer prints "extracting…" or the count itself — those come from the events.

- [ ] **Step 1: Render the new events in `_print_event`**

In `src/dojo/cli/run.py`, replace [cli/run.py:217-241](../../src/dojo/cli/run.py#L217-L241) (`_print_event`) with:

```python
def _print_event(event: AgentEvent) -> None:
    """Render a single agent event in human-readable form."""
    et = event.event_type
    data = event.data

    if et == "text":
        console.print(data.get("text", ""), style="white")
    elif et == "tool_call":
        tool = data.get("tool", "?")
        console.print(f"  [blue]→[/blue] [bold]{tool}[/bold]", style="blue")
    elif et == "tool_result":
        tool = data.get("tool", "?")
        console.print(f"  [green]←[/green] {tool}", style="dim green")
    elif et == "error":
        console.print(f"  [red]error:[/red] {data.get('error', 'unknown')}")
    elif et == "result":
        cost = data.get("cost_usd")
        turns = data.get("turns", 0)
        bits = [f"turns={turns}"]
        if cost is not None:
            bits.append(f"cost=${cost:.4f}")
        console.print(f"\n[dim]result: {', '.join(bits)}[/dim]")
    elif et == "knowledge_flush_started":
        console.print("[dim]saving durable knowledge from this session…[/dim]")
    elif et == "knowledge_flush_completed":
        if "error" in data:
            console.print(f"[dim]knowledge extraction skipped: {data['error']}[/dim]")
        else:
            count = int(data.get("count", 0))
            if count:
                console.print(
                    f"[green]✓[/green] saved {count} knowledge atom(s) from this session"
                )
            else:
                console.print("[dim]no durable findings worth saving[/dim]")
    elif et == "run_finalized":
        # Sentinel — drives SSE termination, no terminal output needed.
        pass
    else:
        console.print(f"  [dim]{et}[/dim]")
```

- [ ] **Step 2: Drop redundant prints from `_graceful_stop`**

Replace [cli/run.py:246-283](../../src/dojo/cli/run.py#L246-L283) (`_graceful_stop`) with:

```python
async def _graceful_stop(
    orchestrator: AgentOrchestrator,
    run_obj: AgentRun,
    lab: LabEnvironment,
    sigint_count: dict,
) -> None:
    """Interrupt the agent, then extract durable findings as knowledge atoms.

    The flush itself emits ``knowledge_flush_started`` / ``knowledge_flush_completed``
    events into ``run_obj.events``; ``_print_event`` renders them. We don't
    print here — that would duplicate the indicator on dual-flush paths.

    A second Ctrl-C during this window short-circuits the cleanup so the
    user is never trapped waiting on the LLM.
    """
    try:
        await orchestrator.stop()
    except Exception as e:
        logger.warning("graceful_stop_interrupt_error", error=str(e))

    if sigint_count["n"] >= 2:
        return

    try:
        await orchestrator.flush_knowledge(run_obj)
    except (asyncio.CancelledError, Exception) as e:
        logger.warning("graceful_stop_extract_failed", error=str(e))
```

- [ ] **Step 3: Drain remaining events in `_stream_events` so flush prints appear**

Today `_stream_events` returns when `stop_requested` is set, *before* the SIGINT-driven flush has emitted its events. The new flush is driven by `_graceful_stop` which calls `orchestrator.flush_knowledge` synchronously — events land in `run_obj.events`, then `await asyncio.wait_for(execute_task, ...)` runs at the call site. Without changes here, the CLI never re-renders those events.

Track how many events `_stream_events` already rendered so the post-stop block can render the rest. Update the helper to return that count:

```python
async def _stream_events(
    run_obj: AgentRun,
    execute_task: asyncio.Task,
    stop_requested: asyncio.Event,
) -> int:
    """As before. Returns the number of events already rendered."""
    seen = 0
    terminal_states = {RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.STOPPED}

    while True:
        while seen < len(run_obj.events):
            _print_event(run_obj.events[seen])
            seen += 1

        if execute_task.done() and run_obj.status in terminal_states:
            while seen < len(run_obj.events):
                _print_event(run_obj.events[seen])
                seen += 1
            return seen

        if stop_requested.is_set():
            return seen

        await asyncio.sleep(0.1)
```

And update the caller:

```python
    try:
        seen = await _stream_events(run_obj, execute_task, stop_requested)
    finally:
        with contextlib.suppress(NotImplementedError):
            loop.remove_signal_handler(signal.SIGINT)

    if stop_requested.is_set() and run_obj.status in (RunStatus.RUNNING, RunStatus.STOPPED):
        await _graceful_stop(orchestrator, run_obj, lab, sigint_count)
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await asyncio.wait_for(execute_task, timeout=2.0)
        # Render any events emitted by the flush / finalization that
        # arrived after _stream_events returned on stop_requested.
        for ev in run_obj.events[seen:]:
            _print_event(ev)
```

Make sure `_stream_events`'s signature change matches both call sites — there's only one in the file.

- [ ] **Step 4: Manual smoke test (terminal)**

In one terminal:
```bash
just run-stub
```
In another terminal, after the stub starts emitting events:
```bash
DOJO_PROJECT_DIR=. uv run dojo stop
```
Expected output in the original terminal:
- A `saving durable knowledge from this session…` line.
- Either `✓ saved N knowledge atom(s) from this session` or `no durable findings worth saving` (the stub backend has no `complete` so the value will be 0 — that's fine).
- Final `■ run stopped (...)` summary.

For SIGINT:
```bash
just run-stub
# Ctrl-C once
```
Expected:
- `[yellow]■[/yellow] stop requested — finishing up (Ctrl-C again to abort cleanup)` (unchanged hint).
- `saving durable knowledge from this session…`.
- Count or skip line.
- Final summary.

- [ ] **Step 5: Run full test suite + lint**

```bash
just test && just lint
```
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/dojo/cli/run.py
git commit -m "feat(cli): render flush events; drop duplicate inline prints from graceful-stop"
```

---

## Task 7: Final verification

- [ ] **Step 1: Run full test + lint suite one more time**

```bash
just test && just lint
```
Expected: PASS.

- [ ] **Step 2: Real-backend smoke test (Claude)**

If you have Claude CLI auth on this machine and a frozen domain available:

```bash
just run-claude
# Let it run for ~10 events, then in another terminal:
DOJO_PROJECT_DIR=. uv run dojo stop
```
Expected:
- The CLI shows `saving durable knowledge from this session…` shortly after the stop sentinel is observed (within 1-2 seconds, not 30).
- Eventually `✓ saved N knowledge atom(s) from this session` with `N ≤ 5`.
- Final stopped summary.
- In `.dojo/memory/`, atom files are present and content is *transferable* (no dataset-shape descriptions).

- [ ] **Step 3: SSE smoke test (server path)**

```bash
just run &
# in another terminal, against the same lab:
curl -N http://127.0.0.1:8000/agent/runs/{some-run-id}/events
```
After a stop on that run, expected: SSE stream emits `knowledge_flush_started`, `knowledge_flush_completed` (with `count` or `error`), then `run_finalized`, then `done`. No truncation.

- [ ] **Step 4: Verify log lines from the linker**

Tail logs during a real run; after a `write_knowledge` call expect to see:
- one `knowledge_atom_created` line
- one `knowledge_link_created` line per link (≥1 for the `CREATED_BY` link, 0+ for `RELATED_TO`)
- no `knowledge_linked` lines anywhere

- [ ] **Step 5: Done — open a PR**

Use the project's release workflow ([docs/RELEASING.md](../../RELEASING.md)) when ready to ship; this PR is feature-only and does not require a version bump on its own.

---

## Self-Review

**Spec coverage:**
- §1 Tighten flush prompt → Task 3.
- §2 Show indicator on every stop path → Task 4 (events) + Task 5 (SSE delivery) + Task 6 (CLI rendering).
- §3 Split atom/link log events → Task 2.
- §4 SSE symmetry check → Task 5 (the "verify" turned into a small fix because SSE was terminating before flush events).
- LLM-linker follow-up → out of scope, tracked in spec.

All spec items have implementing tasks.

**Placeholder check:** No TBDs, no "implement appropriate", no "similar to Task N". Each step contains the exact code or command needed.

**Type consistency:** `flush_run_knowledge` signature uses `events: list[AgentEvent]` everywhere it's referenced. `AgentEvent` is the existing dataclass. Event-type strings (`knowledge_flush_started`, `knowledge_flush_completed`, `run_finalized`, `knowledge_atom_created`, `knowledge_link_created`) are used identically in producer code, CLI rendering, and SSE / tests.

**Out-of-scope reminders:** Don't tune keyword linker thresholds (Task 2 is log-event-only). Don't add new link types. Don't touch the LLM-linker design — that's a separate PR after a data-model review.
