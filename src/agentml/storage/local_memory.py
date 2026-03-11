"""Local memory store — JSON file with keyword search."""

import json
from pathlib import Path

from agentml.core.knowledge import KnowledgeAtom
from agentml.interfaces.memory_store import MemoryStore
from agentml.utils.serialization import to_json


class LocalMemoryStore(MemoryStore):
    """Stores knowledge atoms in a JSON file with keyword-based search."""

    def __init__(self, base_dir: Path | None = None) -> None:
        self.base_dir = base_dir or Path(".agentml/memory")
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._file = self.base_dir / "atoms.json"
        self._atoms: dict[str, KnowledgeAtom] = {}
        self._load_from_disk()

    def _load_from_disk(self) -> None:
        """Load atoms from disk if they exist."""
        if self._file.exists():
            data = json.loads(self._file.read_text())
            for item in data:
                self._atoms[item["id"]] = self._from_dict(item)

    def _save_to_disk(self) -> None:
        """Persist atoms to disk."""
        self._file.write_text(to_json(list(self._atoms.values())))

    async def add(self, atom: KnowledgeAtom) -> str:
        """Add a knowledge atom."""
        self._atoms[atom.id] = atom
        self._save_to_disk()
        return atom.id

    async def search(self, query: str, *, limit: int = 10) -> list[KnowledgeAtom]:
        """Search atoms by keyword matching on context, claim, and action."""
        query_lower = query.lower()
        keywords = query_lower.split()

        scored: list[tuple[int, KnowledgeAtom]] = []
        for atom in self._atoms.values():
            text = f"{atom.context} {atom.claim} {atom.action}".lower()
            score = sum(1 for kw in keywords if kw in text)
            if score > 0:
                scored.append((score, atom))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [atom for _, atom in scored[:limit]]

    async def list(self) -> list[KnowledgeAtom]:
        """List all knowledge atoms."""
        return list(self._atoms.values())

    async def delete(self, atom_id: str) -> bool:
        """Delete a knowledge atom."""
        if atom_id in self._atoms:
            del self._atoms[atom_id]
            self._save_to_disk()
            return True
        return False

    async def get(self, atom_id: str) -> KnowledgeAtom | None:
        """Get a single knowledge atom by ID."""
        return self._atoms.get(atom_id)

    async def update(self, atom: KnowledgeAtom) -> str:
        """Update an existing knowledge atom."""
        self._atoms[atom.id] = atom
        self._save_to_disk()
        return atom.id

    @staticmethod
    def _from_dict(data: dict) -> KnowledgeAtom:
        """Reconstruct a KnowledgeAtom from a dictionary."""
        from datetime import datetime

        return KnowledgeAtom(
            id=data["id"],
            context=data.get("context", ""),
            claim=data.get("claim", ""),
            action=data.get("action", ""),
            confidence=data.get("confidence", 0.0),
            evidence_ids=data.get("evidence_ids", []),
            version=data.get("version", 1),
            supersedes=data.get("supersedes"),
            created_at=datetime.fromisoformat(data["created_at"])
            if "created_at" in data
            else datetime.now(),
            updated_at=datetime.fromisoformat(data["updated_at"])
            if "updated_at" in data
            else datetime.now(),
        )
