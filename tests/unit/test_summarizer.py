"""Unit tests for end-of-run knowledge flush."""

from __future__ import annotations

import json

from dojo.agents.backend import AgentBackend
from dojo.agents.summarizer import extract_knowledge_atoms


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
    assert "3-5 atoms" in captured["prompt"]


async def test_more_than_five_atoms_truncated():
    """Backstop: if the model returns more than 5 atoms, we keep at most 5."""
    backend = _FakeBackend(
        json.dumps([{"claim": f"finding {i}", "confidence": 0.8} for i in range(10)])
    )
    atoms = await extract_knowledge_atoms(backend, transcript="x", domain_id="d")
    assert len(atoms) <= 5


async def test_non_numeric_confidence_treated_as_default():
    """LLM returning non-numeric or null confidence must not lose the whole batch.

    Falls back to default 0.5, which passes the strict-less-than floor.
    """
    backend = _FakeBackend(
        json.dumps(
            [
                {"claim": "string-confidence atom", "confidence": "high"},
                {"claim": "null-confidence atom", "confidence": None},
                {"claim": "good atom", "confidence": 0.9},
            ]
        )
    )
    atoms = await extract_knowledge_atoms(backend, transcript="x", domain_id="d")
    claims = [a["claim"] for a in atoms]
    assert "string-confidence atom" in claims
    assert "null-confidence atom" in claims
    assert "good atom" in claims
