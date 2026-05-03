"""Unit tests for cli/state.py."""

from __future__ import annotations

from pathlib import Path

import pytest

from dojo.cli.state import (
    CLIState,
    CLIStateError,
    get_current_domain_id,
    load_state,
    resolve_domain,
    save_state,
    set_current_domain_id,
    set_current_run_id,
)
from dojo.core.domain import Domain
from dojo.runtime.lab import LabEnvironment


def test_load_missing_state_returns_empty(tmp_path: Path):
    state = load_state(tmp_path)
    assert state.current_domain_id is None
    assert state.current_run_id is None


def test_save_and_load_round_trip(tmp_path: Path):
    save_state(tmp_path, CLIState(current_domain_id="d1", current_run_id="r1"))
    loaded = load_state(tmp_path)
    assert loaded.current_domain_id == "d1"
    assert loaded.current_run_id == "r1"


def test_set_current_domain_id_creates_dir(tmp_path: Path):
    base = tmp_path / "nonexistent"
    set_current_domain_id(base, "abc")
    assert get_current_domain_id(base) == "abc"


def test_set_current_run_id_preserves_domain(tmp_path: Path):
    set_current_domain_id(tmp_path, "d1")
    set_current_run_id(tmp_path, "r1")
    state = load_state(tmp_path)
    assert state.current_domain_id == "d1"
    assert state.current_run_id == "r1"


def test_load_state_rejects_non_mapping(tmp_path: Path):
    (tmp_path / "state.yaml").write_text("- a list\n- of items\n")
    with pytest.raises(CLIStateError):
        load_state(tmp_path)


async def test_resolve_domain_uses_current_when_no_override(lab: LabEnvironment, tmp_path: Path):
    domain = Domain(name="alpha")
    await lab.domain_store.save(domain)
    set_current_domain_id(tmp_path, domain.id)

    resolved = await resolve_domain(lab, base_dir=tmp_path)
    assert resolved.id == domain.id


async def test_resolve_domain_override_by_id(lab: LabEnvironment, tmp_path: Path):
    domain = Domain(name="alpha")
    await lab.domain_store.save(domain)

    resolved = await resolve_domain(lab, base_dir=tmp_path, override=domain.id)
    assert resolved.id == domain.id


async def test_resolve_domain_override_by_name(lab: LabEnvironment, tmp_path: Path):
    domain = Domain(name="alpha")
    await lab.domain_store.save(domain)

    resolved = await resolve_domain(lab, base_dir=tmp_path, override="alpha")
    assert resolved.id == domain.id


async def test_resolve_domain_no_state_raises(lab: LabEnvironment, tmp_path: Path):
    with pytest.raises(CLIStateError, match="No current domain"):
        await resolve_domain(lab, base_dir=tmp_path)


async def test_resolve_domain_stale_pointer_raises(lab: LabEnvironment, tmp_path: Path):
    set_current_domain_id(tmp_path, "ghost-id")
    with pytest.raises(CLIStateError, match="no longer exists"):
        await resolve_domain(lab, base_dir=tmp_path)


async def test_resolve_domain_unknown_override_raises(lab: LabEnvironment, tmp_path: Path):
    with pytest.raises(CLIStateError, match="No domain matches"):
        await resolve_domain(lab, base_dir=tmp_path, override="ghost")
