# Tighten knowledge flush, fix stop UX, split atom/link logging

**Date:** 2026-05-05
**Status:** Approved, ready for implementation plan
**Affects:** end-of-run knowledge extraction, keyword linker, CLI stop UX, log events

## Problem

A `dojo stop` test session produced four issues that compound into bad UX and low-signal knowledge:

1. **Silent flush.** Stopping via `dojo stop` (cross-process) waited 15-30s with no terminal output before atoms appeared in the log. The "extracting durable knowledge…" indicator only prints in the SIGINT path ([cli/run.py:265](../../../src/dojo/cli/run.py#L265)), not when the stop sentinel is observed by `_watch_for_stop_signal`.
2. **Over-eager flush.** A single stopped run produced 8 atoms, several of which described the dataset rather than transferable lessons:
   > "Dataset has 135 features, 5.2M rows, only 1 price lag (24h), and lead_time is in the index but not used as a feature."
   This is run-local context, not knowledge that should travel forward. The flush prompt at [summarizer.py:41-59](../../../src/dojo/agents/summarizer.py#L41-L59) does not reject dataset-shape facts and has no count cap.
3. **Misleading log event.** The keyword linker emits `knowledge_linked` for every atom, even when zero links were created ([keyword_linker.py:97](../../../src/dojo/runtime/keyword_linker.py#L97)). Atom creation and link creation are conflated.
4. **Zero links across 8 atoms.** The keyword overlap threshold (≥40% of smaller word set, ≥3 overlapping words — [keyword_linker.py:20-22](../../../src/dojo/runtime/keyword_linker.py#L20-L22)) almost never triggers on flush atoms because they describe different topics. The candidate set is also capped at the top-5 by recency from `_memory.search`, crowding out relevant older atoms.

Underlying design clarification needed: a knowledge atom today is global at storage (no `domain_id` field on `KnowledgeAtom`) but accessed per-domain via `CREATED_BY` links. Retrieval at run-start ([orchestrator.py:108](../../../src/dojo/agents/orchestrator.py#L108)) loads only same-domain atoms. This is fine and stays — but the linker needs a meaningful definition of "related" that doesn't depend on shared vocabulary.

## Goal

After this change, a stopped run produces few, high-quality atoms; the user sees that the flush is happening; logs distinguish atom creation from link creation; and we have a clear plan to replace keyword matching with LLM-based linking.

## Design

Four fixes ship now. One follow-up (LLM linker) is specified here but tracked separately, and requires a data-model review before implementation.

### 1. Tighten the flush prompt

Rewrite [summarizer.py](../../../src/dojo/agents/summarizer.py) `extract_knowledge_atoms` to:

- Demand **transferable findings only**: modeling lessons, dead-ends, anti-patterns, environment gotchas. Explicitly reject:
  - Dataset shape descriptions (row count, column count, schema)
  - Specific hyperparameter values from one run ("tried n_estimators=1000")
  - Running totals or progress recaps
  - Single-experiment numeric results without comparison context
- Cap output at **3-5 atoms** maximum. The prompt instructs the LLM to pick the highest-signal findings if it has more candidates.
- Demand calibrated `confidence`: ≥0.7 means "I'd bet on this in the next run", ≤0.3 means "weak signal, log only if novel".
- Drop atoms with `confidence < 0.5` after parsing, as a backstop against an over-confident model.

Output format and JSON schema unchanged — this is a prompt-only edit plus a confidence filter at the call site.

### 2. Show "saving knowledge…" indicator on every stop path

Reuse the existing `AgentEvent` infrastructure — no new types, no architectural change. `AgentEvent.event_type` is already a free-form string ([agents/types.py:31](../../../src/dojo/agents/types.py#L31)) and `run.events` is the same list the CLI polls and the SSE stream reads. We just emit two new `event_type` strings into it.

Concretely:

- In [agents/summarizer.py](../../../src/dojo/agents/summarizer.py) `flush_run_knowledge`, append two events to the existing `run.events` list (passed in as a parameter, or via callback — the orchestrator already has the list at hand):
  - `event_type="knowledge_flush_started"` before the LLM call.
  - `event_type="knowledge_flush_completed"` after, with `data={"count": N}` (or `{"error": str}` if extraction raised).
- The orchestrator's `flush_knowledge` ([orchestrator.py:240](../../../src/dojo/agents/orchestrator.py#L240)) passes the run's event list through.
- In [cli/run.py](../../../src/dojo/cli/run.py) `_print_event`, add two `elif` branches for the new strings:
  - `knowledge_flush_started` → "saving durable knowledge from this session…"
  - `knowledge_flush_completed` → "✓ saved N knowledge atom(s)" / "no durable findings worth saving" / "knowledge extraction skipped: {error}".

`_stream_events` already polls `run.events` until `execute_task.done()`. The orchestrator's finally-block flush runs *inside* `execute()`, so the new events land in `run.events` before the task completes and the polling loop renders them in order with no new termination logic.

The SIGINT path keeps its existing "Ctrl-C again to skip" hint (printed by the SIGINT handler, not by `_graceful_stop`). `_graceful_stop` no longer prints the "extracting…" or "✓ saved N…" lines itself — it just invokes `flush_knowledge`, which now emits the events. This removes the duplicate-print risk from the existing code (today both `_graceful_stop` and the orchestrator's finally flush could fire; with idempotence the second is a no-op, but the print could double).

### 3. Split atom-created from link-created log events

In [runtime/keyword_linker.py](../../../src/dojo/runtime/keyword_linker.py) `produce_knowledge`:

- Replace the single `knowledge_linked` log line with:
  - `knowledge_atom_created` after `_memory.add(atom)` — always emitted. Fields: `atom_id`, `domain_id`, `experiment_id`, `confidence`.
  - `knowledge_link_created` once per link written — fields: `atom_id`, `link_type`, `related_atom_id` (if applicable), `domain_id`, `experiment_id`.
- Drop the trailing aggregate `knowledge_linked` event.

`knowledge_flushed` (the count event from `flush_run_knowledge`) stays as-is — it summarises a batch.

Update any callers/tests that assert the old event name.

### 4. CLI/server symmetry check (small, scoped)

The orchestrator's `execute()` finally-block flush already runs for *every* terminal path including server-driven stops. Confirm the server's SSE stream surfaces `knowledge_atom_created`, `knowledge_link_created`, `knowledge_flush_started`, and `knowledge_flush_completed` events the frontend can render later — no frontend work in this PR, just verify nothing in the SSE filter strips them.

We deliberately *do not* tune the keyword linker thresholds. Until the LLM linker lands the experience stays "rarely links" — that's acceptable because flush atoms are now few and high-quality, and over-linking on bad similarity signal would be worse than under-linking.

## Next step (separate PR): LLM-based linker

The keyword linker is a placeholder. It only catches lexical overlap, not semantic similarity, and never will: "GBM beat linear" and "tree models outperform on tabular" should link, and they never share enough words.

Replace it with an `LLMKnowledgeLinker` that:

- Implements the same `KnowledgeLinker` interface ([interfaces/knowledge_linker.py](../../../src/dojo/interfaces/knowledge_linker.py)) — drop-in via DI.
- On `produce_knowledge`:
  1. Always create the new atom (unchanged).
  2. Pull a candidate pool of existing atoms (same-domain atoms plus high-confidence cross-domain atoms, bounded by recency to keep prompt size sane).
  3. Single LLM call: "Here is a new finding `<context/claim>`. Here are existing findings, each with id and one-line claim. Return a JSON list of ids that say *substantively the same thing or directly contradict it*. Empty list is the expected output."
  4. For each returned id, write a `RELATED_TO` link.
- On `find_similar`: same logic without the link writes (used by other code paths today).

This unlocks the design property the user wants: **quality over quantity, with high-precision links**.

> **Design review needed before building this.** The atom + link model is starting to look like a small RAG / knowledge graph. Before scheduling implementation, we should review the data model end-to-end with the question "is this graph queryable in the ways we'll want it 6 months from now?" — including: how knowledge gets packed into the system prompt (retrieval ranking, group collapse, freshness), whether atoms need versioning beyond the existing `version`/`supersedes` fields, whether cross-domain retrieval needs explicit boost/decay, and whether the link types we have today (`CREATED_BY`, `RELATED_TO`) are sufficient or whether group-representation needs its own type. Skipping that review and bolting LLM linking onto the current shape risks locking us into a structure we'll have to migrate out of.

Out of scope for this PR. Tracked as a follow-up; design lives here so the team can grab it when scheduled.

### Why split now

- The fixes in this PR are mechanical and shippable as a single change.
- The LLM linker is a behaviour change that needs its own validation (cost per atom, latency budget at run-start, prompt design, fallback when LLM unavailable) *and* the data-model review above. Don't entangle it with the UX/log-event cleanup.

## Files touched in this PR

| File | Change |
|---|---|
| `src/dojo/agents/summarizer.py` | Rewrite extraction prompt; add confidence filter on parsed atoms; emit `knowledge_flush_started` / `knowledge_flush_completed` events into the run's event list. |
| `src/dojo/agents/orchestrator.py` | Pass `run.events` through to `flush_run_knowledge`. |
| `src/dojo/cli/run.py` | Render the two new event-type strings in `_print_event`; remove the now-redundant inline prints from `_graceful_stop`; keep the "Ctrl-C again to skip" hint in the SIGINT handler. |
| `src/dojo/runtime/keyword_linker.py` | Split the single `knowledge_linked` log line into `knowledge_atom_created` (always) and `knowledge_link_created` (per link). |
| `tests/unit/test_keyword_linker.py` | Update assertions for new event names. |
| `tests/unit/test_summarizer.py` (new or extend) | Test confidence filter; test prompt cap behaviour with fake backend returning 10 atoms; test that flush-start/completed events get appended. |
| `tests/integration/test_stop_flow.py` (new or extend) | Assert that the `dojo stop` path produces the `knowledge_flush_started` and `knowledge_flush_completed` events on the run and that the count is ≤5. |

## Out of scope

- LLM-based linker (specified above, separate PR).
- Cross-domain knowledge surfacing in the system prompt — today only same-domain atoms load; that stays.
- Frontend rendering of new log events.
- Keyword linker threshold tuning — left as-is on purpose (see §4).
- Memory store search ranking changes (recency vs relevance).
- Removing `KnowledgeAtom`-level `domain_id` ambiguity — design intent (global pool, per-domain links) is unchanged and remains correct.

## Open questions

- Confidence floor of 0.5 vs 0.6: the flush prompt gives the LLM a calibration anchor; in practice it tends to return 0.6-0.8. 0.5 is permissive enough to keep the floor a backstop, not a primary filter. Will revisit after a few real sessions.
