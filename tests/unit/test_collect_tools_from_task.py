"""Phase 3: collect_all_tools reads from domain.task.tools, not domain.tools."""

from __future__ import annotations

from dojo.core.domain import Domain, DomainTool, ToolType, VerificationResult
from dojo.core.task import Task, TaskType
from dojo.tools.domain_tools import _normalize_params, create_domain_tools


def _exec_tool(name: str) -> DomainTool:
    return DomainTool(
        name=name,
        type=ToolType.DATA_LOADER,
        executable=True,
        code="print('{}')",
        verification=VerificationResult(verified=True),
    )


def test_collect_reads_task_tools_when_task_set(lab):
    domain = Domain(
        name="d",
        tools=[_exec_tool("legacy_tool")],
        task=Task(type=TaskType.REGRESSION, tools=[_exec_tool("load_data")]),
    )
    tool_defs = create_domain_tools(lab, domain)
    names = {t.name for t in tool_defs}
    assert names == {"load_data"}


def test_collect_falls_back_to_domain_tools_when_no_task(lab):
    domain = Domain(name="d", tools=[_exec_tool("legacy_tool")])
    tool_defs = create_domain_tools(lab, domain)
    names = {t.name for t in tool_defs}
    assert names == {"legacy_tool"}


def test_normalize_params_wraps_flat_form():
    out = _normalize_params({"y_pred": {"type": "array"}})
    assert out["type"] == "object"
    assert "y_pred" in out["properties"]


def test_normalize_params_passes_through_already_wrapped():
    schema = {"type": "object", "properties": {"x": {"type": "string"}}}
    out = _normalize_params(schema)
    assert out is schema  # identity preserved


def test_normalize_params_handles_empty():
    assert _normalize_params({}) == {"type": "object", "properties": {}}
