"""End-of-run knowledge extraction — shared by orchestrator and CLI graceful-stop."""

from __future__ import annotations

import json

from dojo.agents.backend import AgentBackend
from dojo.agents.types import AgentEvent
from dojo.runtime.lab import LabEnvironment
from dojo.utils.logging import get_logger

logger = get_logger(__name__)


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
    response can't be parsed.
    """
    prompt = (
        "You are reviewing the transcript of an autonomous ML research agent. "
        "Extract only durable findings that future runs of this domain "
        f"(domain_id={domain_id}) would benefit from knowing.\n\n"
        "Examples of what counts:\n"
        "- 'GradientBoosting beat LinearRegression by ~40% MAE on this dataset' "
        "(carry-forward signal)\n"
        "- 'lightgbm and xgboost are NOT installed in this workspace' (avoid future failures)\n"
        "- 'Quadratic feature engineering hurt HistGBM' (saves dead-end retries)\n\n"
        "Skip routine incremental tuning ('tried n_estimators=1000'). Skip running totals.\n\n"
        "Output ONLY a JSON array (possibly empty) of objects with keys:\n"
        '- "claim": one-sentence finding (required)\n'
        '- "context": short phrase, e.g. "early baseline runs" (optional)\n'
        '- "confidence": float 0.0-1.0 calibrated to evidence (optional)\n'
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
    return [a for a in atoms if isinstance(a, dict) and a.get("claim")]


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
