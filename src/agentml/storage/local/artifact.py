"""Local artifact store — filesystem-based binary storage."""

from pathlib import Path

from agentml.interfaces.artifact_store import ArtifactStore


class LocalArtifactStore(ArtifactStore):
    """Stores binary artifacts on the local filesystem."""

    def __init__(self, base_dir: Path | None = None) -> None:
        self.base_dir = base_dir or Path(".agentml/artifacts")
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, artifact_id: str) -> Path:
        return self.base_dir / artifact_id

    async def save(self, artifact_id: str, data: bytes, *, content_type: str = "") -> str:
        """Save binary artifact to filesystem."""
        path = self._path(artifact_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return str(path)

    async def load(self, artifact_id: str) -> bytes | None:
        """Load binary artifact from filesystem."""
        path = self._path(artifact_id)
        if not path.exists():
            return None
        return path.read_bytes()

    async def list(self, *, prefix: str = "") -> list[str]:
        """List artifact IDs."""
        artifacts = []
        for path in self.base_dir.rglob("*"):
            if path.is_file():
                rel = str(path.relative_to(self.base_dir))
                if rel.startswith(prefix):
                    artifacts.append(rel)
        return artifacts

    async def delete(self, artifact_id: str) -> bool:
        """Delete an artifact file."""
        path = self._path(artifact_id)
        if path.exists():
            path.unlink()
            return True
        return False
