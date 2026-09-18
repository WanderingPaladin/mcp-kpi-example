import pytest
from fastmcp import Client

from app.mcp_server import mcp


@pytest.mark.asyncio
async def test_mcp_lists_expected_tools(engine):
    async with Client(mcp) as client:
        tools = await client.list_tools()
    names = sorted(tool.name for tool in tools)
    assert names == ["get_company_estimates", "get_qtd_snapshots", "search_catalog"]


@pytest.mark.asyncio
async def test_mcp_search_catalog(engine):
    async with Client(mcp) as client:
        result = await client.call_tool("search_catalog", {"query": "IGC"})
    data = result.data
    assert data["ok"] is True
    assert any(company["ticker"] == "IGC" for company in data["companies"])


@pytest.mark.asyncio
async def test_mcp_get_company_estimates_latest_qtd(engine):
    async with Client(mcp) as client:
        result = await client.call_tool(
            "get_company_estimates",
            {"ticker": "igc", "kpi": "Total Revenue ($MM)", "include_history": False},
        )
    snapshot = result.data["latest_qtd"][0]
    assert snapshot["as_of"] == "2026-03-15"
    assert snapshot["period"] == "2026Q1"
    assert snapshot["value"] == "627.45"


@pytest.mark.asyncio
async def test_mcp_unknown_ticker_is_structured(engine):
    async with Client(mcp) as client:
        result = await client.call_tool(
            "get_company_estimates",
            {"ticker": "NOPE"},
            raise_on_error=False,
        )
    assert result.data["ok"] is False
    assert result.data["error"] == "unknown_ticker"
    assert result.data["suggestions"]


@pytest.mark.asyncio
async def test_mcp_qtd_snapshots_drilldown(engine):
    async with Client(mcp) as client:
        result = await client.call_tool(
            "get_qtd_snapshots",
            {"ticker": "IGC", "kpi": "Total Revenue ($MM)", "period": "2026Q1"},
        )
    assert [row["as_of"] for row in result.data["snapshots"]] == [
        "2026-01-31",
        "2026-02-15",
        "2026-02-28",
        "2026-03-15",
    ]
