"""Unit tests for runtime.setup_loader."""

from __future__ import annotations

from pathlib import Path

from dojo.core.domain import Domain
from dojo.runtime.setup_loader import (
    default_setup_template,
    load_setup,
    resolve_setup_path,
    write_setup,
)


def test_resolve_uses_setup_path_when_set(tmp_path: Path):
    custom = tmp_path / "custom.md"
    domain = Domain(name="d", setup_path=str(custom))
    assert resolve_setup_path(domain, base_dir=tmp_path) == custom


def test_resolve_falls_back_to_domain_local(tmp_path: Path):
    domain = Domain(name="d")
    expected = tmp_path / "domains" / domain.id / "SETUP.md"
    assert resolve_setup_path(domain, base_dir=tmp_path) == expected


def test_load_returns_file_content(tmp_path: Path):
    setup = tmp_path / "SETUP.md"
    setup.write_text("## Dataset\nhousing data\n")
    domain = Domain(name="d", setup_path=str(setup))
    assert "housing data" in load_setup(domain, base_dir=tmp_path)


def test_load_returns_empty_when_missing(tmp_path: Path):
    domain = Domain(name="d")
    assert load_setup(domain, base_dir=tmp_path) == ""


def test_load_returns_empty_when_blank(tmp_path: Path):
    setup = tmp_path / "SETUP.md"
    setup.write_text("   \n")
    domain = Domain(name="d", setup_path=str(setup))
    assert load_setup(domain, base_dir=tmp_path) == ""


def test_write_creates_parent_dirs(tmp_path: Path):
    domain = Domain(name="d")
    written = write_setup(domain, "## Dataset\n…\n", base_dir=tmp_path)
    assert written.exists()
    assert written.read_text() == "## Dataset\n…\n"


def test_default_template_has_dataset_and_evaluate_sections(tmp_path: Path):
    domain = Domain(name="california housing", description="predict prices")
    out = default_setup_template(domain)
    assert "california housing" in out
    assert "## Dataset" in out
    assert "## Evaluate" in out
    # Crucially, no agent-steering sections
    assert "## Goal" not in out
    assert "## Success" not in out
