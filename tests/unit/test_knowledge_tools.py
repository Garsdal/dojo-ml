"""Unit tests for knowledge tool handlers."""

from agentml.tools.base import ToolResult
from agentml.tools.knowledge import create_knowledge_tools


async def test_write_knowledge(lab):
    tools = create_knowledge_tools(lab)
    write_tool = next(t for t in tools if t.name == "write_knowledge")

    result = await write_tool.handler(
        {
            "context": "California housing experiment",
            "claim": "Linear regression achieves RMSE of 0.72",
            "action": "Use as baseline",
            "confidence": 0.85,
            "evidence_ids": ["exp-001"],
        }
    )

    assert isinstance(result, ToolResult)
    assert not result.is_error
    assert "atom_id" in result.data
    assert result.data["status"] == "saved"


async def test_write_knowledge_minimal(lab):
    tools = create_knowledge_tools(lab)
    write_tool = next(t for t in tools if t.name == "write_knowledge")

    result = await write_tool.handler(
        {
            "context": "Some context",
            "claim": "Some claim",
        }
    )

    assert not result.is_error
    assert "atom_id" in result.data


async def test_search_knowledge(lab):
    tools = create_knowledge_tools(lab)
    write_tool = next(t for t in tools if t.name == "write_knowledge")
    search_tool = next(t for t in tools if t.name == "search_knowledge")

    await write_tool.handler(
        {
            "context": "Housing experiment",
            "claim": "Ridge regression outperforms linear regression",
        }
    )
    await write_tool.handler(
        {
            "context": "NLP experiment",
            "claim": "BERT embeddings improve accuracy",
        }
    )

    result = await search_tool.handler({"query": "regression"})

    assert not result.is_error
    assert isinstance(result.data, list)
    assert len(result.data) >= 1
    claims = [a["claim"] for a in result.data]
    assert any("regression" in c.lower() for c in claims)


async def test_search_knowledge_with_limit(lab):
    tools = create_knowledge_tools(lab)
    write_tool = next(t for t in tools if t.name == "write_knowledge")
    search_tool = next(t for t in tools if t.name == "search_knowledge")

    for i in range(5):
        await write_tool.handler(
            {
                "context": f"Experiment {i}",
                "claim": f"Finding {i} about regression",
            }
        )

    result = await search_tool.handler({"query": "regression", "limit": 2})

    assert not result.is_error
    assert len(result.data) <= 2


async def test_list_knowledge(lab):
    tools = create_knowledge_tools(lab)
    write_tool = next(t for t in tools if t.name == "write_knowledge")
    list_tool = next(t for t in tools if t.name == "list_knowledge")

    await write_tool.handler(
        {
            "context": "Context A",
            "claim": "Claim A",
        }
    )
    await write_tool.handler(
        {
            "context": "Context B",
            "claim": "Claim B",
        }
    )

    result = await list_tool.handler({})

    assert not result.is_error
    assert isinstance(result.data, list)
    assert len(result.data) == 2


async def test_list_knowledge_empty(lab):
    tools = create_knowledge_tools(lab)
    list_tool = next(t for t in tools if t.name == "list_knowledge")

    result = await list_tool.handler({})

    assert not result.is_error
    assert result.data == []


async def test_tool_definitions_count(lab):
    tools = create_knowledge_tools(lab)
    assert len(tools) == 3
    names = {t.name for t in tools}
    assert names == {"write_knowledge", "search_knowledge", "list_knowledge"}
