"""CLI helper — build a LabEnvironment for in-process CLI commands.

CLI commands are peers of the HTTP API: both call into `LabEnvironment`
services directly. There's no httpx round-trip, so a running server is
optional.
"""

from __future__ import annotations

from pathlib import Path

from dojo.api.deps import build_lab
from dojo.config.settings import Settings
from dojo.runtime.lab import LabEnvironment


def build_cli_lab(config_path: Path | None = None) -> tuple[LabEnvironment, Settings]:
    """Load settings and construct a LabEnvironment for a CLI command.

    Args:
        config_path: Optional path to a config YAML. Defaults to `.dojo/config.yaml`.

    Returns:
        (lab, settings) — caller uses lab to access services and settings to
        read CLI-relevant fields (storage.base_dir, agent.backend, etc.).
    """
    settings = Settings.load(config_path)
    lab = build_lab(settings)
    return lab, settings
