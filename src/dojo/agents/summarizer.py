"""End-of-run knowledge extraction — shared by orchestrator and CLI graceful-stop."""

from __future__ import annotations

import json

from dojo.agents.backend import AgentBackend
from dojo.agents.types import AgentEvent
from dojo.runtime.lab import LabEnvironment
from dojo.utils.logging import get_logger

logger = get_logger(__name__)

# Atoms with confidence below this floor are discarded as a backstop against
# over-confident defaults. The prompt asks the model to calibrate, but we don't
# trust calibration alone.
_CONFIDENCE_FLOOR = 0.5

# Hard cap on flush output. The prompt asks for 3-5; this stops the model from
# returning a larger list when it disregards the instruction.
_MAX_ATOMS = 5


def collect_transcript(events: list[AgentEvent]) -> str:
    """Compress an event list into a transcript suitable for one-shot LLM review."""
    parts: list[str] = []
    for e in events:
        if e.event_type == "text":
            text = e.data.get("text", "")
            if text:
                parts.append(text)
        elif e.event_type == "tool_call":
            tool = e.data.get("tool", "")
            params = json.dumps(e.data.get("input", {}), default=str)[:300]
            parts.append(f"[tool_call] {tool} {params}")
        elif e.event_type == "tool_result":
            content = str(e.data.get("content", ""))[:300]
            parts.append(f"[tool_result] {content}")
    return "\n".join(parts)


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
        "- Modeling lessons that generalise (e.g. 'tree models tend to beat linear on tabular regression')\n"
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
        raw_conf = a.get("confidence", 0.5)
        try:
            confidence = float(raw_conf) if raw_conf is not None else 0.5
        except (TypeError, ValueError):
            confidence = 0.5
        if confidence < _CONFIDENCE_FLOOR:
            continue
        cleaned.append(a)
    return cleaned[:_MAX_ATOMS]


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

    Returns the number of atoms written. Safe to call when the backend can't
    do completions (e.g. the stub) — returns 0 instead of raising.
    """
    transcript = collect_transcript(events)
    if not transcript.strip():
        return 0

    try:
        atoms = await extract_knowledge_atoms(backend, transcript, domain_id)
    except Exception as e:
        logger.warning("knowledge_flush_extract_failed", run_id=run_id, error=str(e))
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

    if written:
        logger.info("knowledge_flushed", run_id=run_id, atoms=written)
    return written
