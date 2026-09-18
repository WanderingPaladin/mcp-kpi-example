"""Independent MCP client: discover tools and call them over HTTP or in-process."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from fastmcp import Client

from app.config import get_settings
from app.mcp_server import mcp


def _print(title: str, payload) -> None:
    print(f"\n=== {title} ===")
    print(json.dumps(payload, indent=2, default=str))


async def run_demo(client: Client) -> None:
    async with client:
        tools = await client.list_tools()
        discovered = [
            {"name": tool.name, "description": (tool.description or "")[:180]}
            for tool in tools
        ]
        _print("discovered_tools", discovered)

        catalog = await client.call_tool("search_catalog", {"query": "software"})
        _print("search_catalog(software)", catalog.data)

        estimates = await client.call_tool(
            "get_company_estimates",
            {"ticker": "IGC", "kpi": "Total Revenue ($MM)", "period_from": "2025Q4"},
        )
        _print("get_company_estimates(IGC, Total Revenue)", estimates.data)

        snapshots = await client.call_tool(
            "get_qtd_snapshots",
            {"ticker": "IGC", "kpi": "Global Net Added Subscribers", "period": "2026Q1"},
        )
        _print("get_qtd_snapshots(IGC subscribers)", snapshots.data)

        unknown = await client.call_tool(
            "get_company_estimates",
            {"ticker": "IGCC"},
            raise_on_error=False,
        )
        _print("unknown_ticker(IGCC)", unknown.data or unknown.content[0].text)


async def main() -> None:
    parser = argparse.ArgumentParser(description="Call the KPI MCP server as an external client")
    parser.add_argument(
        "--url",
        default=None,
        help="Streamable HTTP MCP URL. Default: MCP_URL from env, or in-process if --in-process.",
    )
    parser.add_argument(
        "--in-process",
        action="store_true",
        help="Use the in-process FastMCP server (no HTTP listener required).",
    )
    args = parser.parse_args()

    if args.in_process:
        from app.db import configure_engine, init_db

        configure_engine()
        init_db()
        client = Client(mcp)
    else:
        url = args.url or get_settings().mcp_url
        print(f"Connecting to {url}", file=sys.stderr)
        client = Client(url)

    await run_demo(client)


if __name__ == "__main__":
    asyncio.run(main())
