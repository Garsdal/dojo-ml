# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html)
with the caveat that 0.0.x releases may break the API freely.

`### Agent prompts` is always the first section in a release entry, even when
empty, because prompt and tool-description changes are the highest-stakes
behavioural changes in this codebase. See [docs/RELEASING.md](docs/RELEASING.md)
for the release workflow.

## [Unreleased]

## [v0.0.8] - 2026-05-05

### Agent prompts

- **`write_knowledge` tool description** ([src/dojo/tools/knowledge.py](src/dojo/tools/knowledge.py)) — removed the line "Always do this after experiments", which directly contradicted the prompt's "be selective" guidance. New description gives concrete triggers (rule-out, dead hyperparameter range, feature/preprocessing verdict) and explicitly says "skip routine incremental tuning". Effect: the agent should now have a coherent posture instead of resolving the contradiction by writing nothing.
- **System prompt — `write_knowledge` guidance** ([src/dojo/agents/prompts.py](src/dojo/agents/prompts.py)) — replaced "if and only if... skip routine incremental tuning" with "would a future run of this domain benefit from knowing this? When in doubt, write it" plus a one-line note that an end-of-run extractor exists as a safety net. The double-hedged framing was pushing the model to default to silence; the new framing gives the agent permission to write durable findings without fearing bloat.
- **System prompt — secondary mention** ([src/dojo/agents/prompts.py](src/dojo/agents/prompts.py)) — tightened "Be selective with `write_knowledge` — record only durable findings... don't bloat the store" to "Use `write_knowledge` for durable findings, not per-experiment recaps: one atom per real learning, not one per turn." Same intent, less anxious framing.

### Added

- **End-of-run knowledge flush** ([src/dojo/agents/orchestrator.py](src/dojo/agents/orchestrator.py), [src/dojo/agents/summarizer.py](src/dojo/agents/summarizer.py)) — `AgentOrchestrator.execute()` now runs a one-shot LLM extractor on the run transcript and writes durable findings as knowledge atoms via `lab.knowledge_linker`. Fires for COMPLETED, FAILED, and STOPPED runs. Idempotent via a `_knowledge_flushed` flag so the CLI graceful-stop path doesn't double-write. Silently skips when the backend doesn't support `complete()` (e.g. the stub) or when there's no transcript content. Closes the gap where API-driven runs (`POST /agent/run`) had no knowledge-capture safety net.
- **`flush_run_knowledge` shared helper** ([src/dojo/agents/summarizer.py](src/dojo/agents/summarizer.py)) — extract + write in one call. Used by both the orchestrator's automatic flush and the CLI's Ctrl-C cleanup path.

### Changed

- **CLI graceful-stop delegates to the orchestrator** ([src/dojo/cli/run.py](src/dojo/cli/run.py)) — `_graceful_stop` now calls `orchestrator.flush_knowledge(run)` instead of inlining transcript extraction. Same UX (the "Ctrl-C again to skip" affordance is preserved); the underlying logic now lives in one place.

### Notes

- 7 new unit tests in [tests/unit/test_orchestrator.py](tests/unit/test_orchestrator.py) cover the flush hook across all terminal statuses, idempotency, fence-stripping, and silent failure on `complete()` exceptions.
