from __future__ import annotations

import argparse
import logging
import time
from functools import wraps
from typing import Any, Callable

from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.config import get_settings
from app.db import configure_engine, init_db, session_scope
from app.logging_utils import configure_logging, correlation_id_var, log_tool_call, new_correlation_id
from app.services.kpi import KpiService

logger = logging.getLogger("kpi.mcp")
kpi_service = KpiService()

mcp = FastMCP(
    name="YipitData KPI Server",
    instructions=(
        "Read-only YipitData public-investor KPI estimates. "
        "Discover companies with search_catalog, fetch history plus the latest dated QTD "
        "snapshot with get_company_estimates, and inspect earlier intra-quarter snapshots "
        "with get_qtd_snapshots. QTD is not a completed quarter and is not 'current' "
        "relative to today's calendar date — always keep the fiscal period and as_of date. "
        "This sample's QTD window is 2026Q1; the latest snapshot is 2026-03-15. "
        "Never invent values, growth rates, or full-quarter extrapolations."
    ),
)


def tracked_tool(fn: Callable[..., dict[str, Any]]) -> Callable[..., dict[str, Any]]:
    @wraps(fn)
    def wrapper(**kwargs: Any) -> dict[str, Any]:
        token = correlation_id_var.set(new_correlation_id())
        started = time.perf_counter()
        outcome = "error"
        error = None
        try:
            result = fn(**kwargs)
            outcome = "ok" if result.get("ok", True) else result.get("error", "error")
            return result
        except Exception as exc:
            error = str(exc)
            logger.exception("tool_failed", extra={"tool": fn.__name__})
            return {
                "ok": False,
                "error": "internal_error",
                "message": "The KPI service failed while handling that request. Retry with simpler arguments.",
            }
        finally:
            log_tool_call(
                logger,
                tool=fn.__name__,
                arguments=kwargs,
                outcome=outcome,
                duration_ms=(time.perf_counter() - started) * 1000,
                error=error,
            )
            correlation_id_var.reset(token)

    return wrapper


@mcp.custom_route("/health", methods=["GET"])
async def health_check(_request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok", "server": "YipitData KPI Server"})


@mcp.tool
@tracked_tool
def search_catalog(
    query: str | None = None,
    sector: str | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    """Discover sectors, companies, tickers, and KPI names in the catalog.

    Call this first when the user mentions a company, ticker, sector, or metric
    that you have not confirmed yet. Results are bounded; tighten query or sector
    rather than paging blindly.
    """
    with session_scope() as session:
        return kpi_service.search_catalog(session, query=query, sector=sector, limit=limit)


@mcp.tool
@tracked_tool
def get_company_estimates(
    ticker: str,
    kpi: str | None = None,
    period_from: str | None = None,
    period_to: str | None = None,
    include_history: bool = True,
    include_latest_qtd: bool = True,
    limit: int | None = None,
) -> dict[str, Any]:
    """Return historical quarterly estimates and the latest QTD snapshot for a company.

    Latest QTD means the most recent as_of date for each company/KPI/fiscal period,
    not 'current' relative to today. Sample QTD data is fiscal 2026Q1 with latest
    as_of 2026-03-15. QTD is intra-quarter; do not treat it as a finished quarter
    and do not infer a subscriber growth rate from net-added subscribers.
    Use get_qtd_snapshots when the user wants earlier dated QTD prints.
    """
    with session_scope() as session:
        return kpi_service.get_company_estimates(
            session,
            ticker=ticker,
            kpi=kpi,
            period_from=period_from,
            period_to=period_to,
            include_history=include_history,
            include_latest_qtd=include_latest_qtd,
            limit=limit,
        )


@mcp.tool
@tracked_tool
def get_qtd_snapshots(
    ticker: str,
    kpi: str | None = None,
    period: str | None = None,
    as_of: str | None = None,
    latest_only: bool = False,
    limit: int | None = None,
) -> dict[str, Any]:
    """Inspect quarter-to-date snapshots, including earlier as_of dates.

    Use this to drill into intra-quarter revisions (this sample: 2026-01-31,
    2026-02-15, 2026-02-28, 2026-03-15). as_of is YYYY-MM-DD. latest_only=true
    returns only the newest snapshot per KPI/period. QTD is not a completed quarter.
    """
    with session_scope() as session:
        return kpi_service.get_qtd_snapshots(
            session,
            ticker=ticker,
            kpi=kpi,
            period=period,
            as_of=as_of,
            latest_only=latest_only,
            limit=limit,
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="YipitData KPI MCP server")
    parser.add_argument("--transport", choices=["http", "stdio"], default="http")
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    args = parser.parse_args()

    configure_logging()
    settings = get_settings()
    configure_engine(settings.database_url)
    init_db()

    if args.transport == "stdio":
        mcp.run(transport="stdio")
        return

    mcp.run(
        transport="http",
        host=args.host or settings.mcp_host,
        port=args.port or settings.mcp_port,
        path="/mcp",
    )


if __name__ == "__main__":
    main()
