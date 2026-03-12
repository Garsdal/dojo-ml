"""Local knowledge link store — JSON file persistence for links."""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from agentml.core.knowledge_link import KnowledgeLink, LinkType
from agentml.interfaces.knowledge_link_store import KnowledgeLinkStore
from agentml.utils.serialization import to_json


class LocalKnowledgeLinkStore(KnowledgeLinkStore):
    """Stores knowledge links in JSON files."""

    def __init__(self, base_dir: Path | None = None) -> None:
        self.base_dir = base_dir or Path(".agentml/knowledge_links")
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._links_file = self.base_dir / "links.json"
        self._links: dict[str, KnowledgeLink] = {}
        self._load_from_disk()

    def _load_from_disk(self) -> None:
        if self._links_file.exists():
            data = json.loads(self._links_file.read_text())
            for item in data:
                link = self._link_from_dict(item)
                self._links[link.id] = link

    def _save_links_to_disk(self) -> None:
        self._links_file.write_text(to_json(list(self._links.values())))

    async def link(self, link: KnowledgeLink) -> str:
        self._links[link.id] = link
        self._save_links_to_disk()
        return link.id

    async def unlink(self, link_id: str) -> bool:
        if link_id in self._links:
            del self._links[link_id]
            self._save_links_to_disk()
            return True
        return False

    async def get_links_for_atom(self, atom_id: str) -> list[KnowledgeLink]:
        return [lk for lk in self._links.values() if lk.atom_id == atom_id]

    async def get_links_for_experiment(self, experiment_id: str) -> list[KnowledgeLink]:
        return [lk for lk in self._links.values() if lk.experiment_id == experiment_id]

    async def get_links_for_domain(self, domain_id: str) -> list[KnowledgeLink]:
        return [lk for lk in self._links.values() if lk.domain_id == domain_id]

    @staticmethod
    def _link_from_dict(data: dict[str, Any]) -> KnowledgeLink:
        return KnowledgeLink(
            id=data["id"],
            atom_id=data.get("atom_id", ""),
            experiment_id=data.get("experiment_id", ""),
            domain_id=data.get("domain_id", ""),
            link_type=LinkType(data.get("link_type", "created_by")),
            related_atom_id=data.get("related_atom_id"),
            created_at=datetime.fromisoformat(data["created_at"])
            if "created_at" in data
            else datetime.now(),
        )
