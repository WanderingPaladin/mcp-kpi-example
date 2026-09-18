from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.models import KpiEstimate
from app.services.matching import (
    CompanyRef,
    list_companies,
    list_kpis_for_ticker,
    resolve_ticker,
    suggest_kpis,
)

PERIOD_RE = re.compile(r"^(\d{4})Q([1-4])$")
MAX_LIMIT = 500
DEFAULT_CATALOG_LIMIT = 20
DEFAULT_ESTIMATE_LIMIT = 200
DEFAULT_QTD_LIMIT = 100


def serialize_value(value: Decimal) -> str:
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def serialize_row(row: KpiEstimate) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "ticker": row.ticker,
        "company_name": row.company_name,
        "sector": row.sector,
        "kpi": row.kpi,
        "unit": row.unit,
        "period": row.period,
        "period_start": row.period_start.isoformat(),
        "period_end": row.period_end.isoformat(),
        "estimate_type": row.estimate_type,
        "value": serialize_value(row.value),
        "as_of": row.as_of.isoformat() if row.as_of else None,
    }
    return payload


def parse_period(value: str | None, field_name: str) -> dict[str, Any] | None:
    if value is None or value == "":
        return None
    raw = value.strip().upper()
    if not PERIOD_RE.match(raw):
        return {
            "ok": False,
            "error": "invalid_period",
            "message": (
                f"{field_name} must look like 2026Q1 (year + Q1-Q4). Received {value!r}."
            ),
        }
    return {"ok": True, "period": raw}


def parse_iso_date(value: str | None, field_name: str) -> dict[str, Any]:
    if value is None or value == "":
        return {"ok": True, "date": None}
    raw = value.strip()
    try:
        return {"ok": True, "date": datetime.strptime(raw, "%Y-%m-%d").date()}
    except ValueError:
        return {
            "ok": False,
            "error": "invalid_date",
            "message": f"{field_name} must be YYYY-MM-DD. Received {value!r}.",
        }


def clamp_limit(limit: int | None, default: int) -> dict[str, Any]:
    if limit is None:
        return {"ok": True, "limit": default}
    if limit < 1:
        return {
            "ok": False,
            "error": "invalid_limit",
            "message": "limit must be a positive integer.",
        }
    return {"ok": True, "limit": min(limit, MAX_LIMIT)}


def period_tuple(period: str) -> tuple[int, int]:
    match = PERIOD_RE.match(period)
    if not match:
        return (0, 0)
    return int(match.group(1)), int(match.group(2))


def unknown_ticker_error(ticker: str, suggestions: list[CompanyRef]) -> dict[str, Any]:
    return {
        "ok": False,
        "error": "unknown_ticker",
        "ticker": ticker,
        "message": (
            f"No company found for ticker {ticker!r}. "
            "Use search_catalog to discover valid tickers."
        ),
        "suggestions": [
            {
                "ticker": item.ticker,
                "company_name": item.company_name,
                "sector": item.sector,
            }
            for item in suggestions
        ],
    }


def unknown_kpi_error(kpi: str, available: list[str], suggestions: list[str]) -> dict[str, Any]:
    return {
        "ok": False,
        "error": "unknown_kpi",
        "kpi": kpi,
        "message": (
            f"No KPI matching {kpi!r}. Do not invent a metric. "
            "Choose one of the available KPIs, or inspect QTD net-added subscribers "
            "instead of inferring a growth rate."
        ),
        "available_kpis": available,
        "suggestions": suggestions,
    }


def resolve_kpi(session: Session, ticker: str, kpi: str | None) -> dict[str, Any]:
    available = list_kpis_for_ticker(session, ticker)
    if not kpi or not kpi.strip():
        return {"ok": True, "kpi": None, "available_kpis": available}

    needle = kpi.strip()
    exact = next((item for item in available if item.lower() == needle.lower()), None)
    if exact:
        return {"ok": True, "kpi": exact, "available_kpis": available}

    unique_substring = [item for item in available if needle.lower() in item.lower()]
    if len(unique_substring) == 1:
        return {"ok": True, "kpi": unique_substring[0], "available_kpis": available}

    from app.services.matching import KPI_ALIASES, normalize

    alias_hits = [item for item in KPI_ALIASES.get(normalize(needle), []) if item in available]
    if len(alias_hits) == 1:
        return {"ok": True, "kpi": alias_hits[0], "available_kpis": available}

    suggestions = suggest_kpis(available, needle)
    if alias_hits:
        suggestions = list(dict.fromkeys(alias_hits + suggestions))
    return unknown_kpi_error(needle, available, suggestions)


class KpiService:
    def search_catalog(
        self,
        session: Session,
        query: str | None = None,
        sector: str | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        limit_result = clamp_limit(limit, DEFAULT_CATALOG_LIMIT)
        if not limit_result["ok"]:
            return limit_result
        capped = limit_result["limit"]

        companies = list_companies(session)
        sectors = sorted({company.sector for company in companies})
        if sector:
            sector_matches = [item for item in sectors if item.lower() == sector.strip().lower()]
            if not sector_matches:
                close = [
                    item
                    for item in sectors
                    if sector.strip().lower() in item.lower()
                ]
                return {
                    "ok": False,
                    "error": "unknown_sector",
                    "sector": sector,
                    "message": f"No sector named {sector!r}.",
                    "suggestions": close or sectors,
                }
            companies = [company for company in companies if company.sector == sector_matches[0]]
            sectors = [sector_matches[0]]

        if query and query.strip():
            needle = query.strip().lower()
            companies = [
                company
                for company in companies
                if needle in company.ticker.lower()
                or needle in company.company_name.lower()
                or needle in company.sector.lower()
            ]
            kpi_rows = session.execute(
                select(KpiEstimate.ticker, KpiEstimate.kpi, KpiEstimate.unit)
                .where(KpiEstimate.kpi.ilike(f"%{query.strip()}%"))
                .distinct()
            ).all()
            extra_tickers = {row.ticker for row in kpi_rows}
            if extra_tickers:
                by_ticker = {company.ticker: company for company in list_companies(session)}
                for ticker in extra_tickers:
                    if ticker in by_ticker and all(c.ticker != ticker for c in companies):
                        companies.append(by_ticker[ticker])

        companies = sorted(companies, key=lambda item: item.ticker)[:capped]

        kpi_units = session.execute(
            select(KpiEstimate.kpi, KpiEstimate.unit).distinct().order_by(KpiEstimate.kpi)
        ).all()
        catalog_kpis = [{"kpi": row.kpi, "unit": row.unit} for row in kpi_units]

        payload_companies = []
        for company in companies:
            payload_companies.append(
                {
                    "ticker": company.ticker,
                    "company_name": company.company_name,
                    "sector": company.sector,
                    "kpis": list_kpis_for_ticker(session, company.ticker),
                }
            )

        return {
            "ok": True,
            "query": query,
            "sectors": sectors,
            "companies": payload_companies,
            "kpis": catalog_kpis,
            "returned": len(payload_companies),
            "truncated": len(payload_companies) == capped,
            "note": (
                "QTD coverage in this sample is fiscal 2026Q1. The latest snapshot "
                "date is 2026-03-15; do not describe it as current relative to today."
            ),
        }

    def get_company_estimates(
        self,
        session: Session,
        ticker: str,
        kpi: str | None = None,
        period_from: str | None = None,
        period_to: str | None = None,
        include_history: bool = True,
        include_latest_qtd: bool = True,
        limit: int | None = None,
    ) -> dict[str, Any]:
        if not ticker or not ticker.strip():
            return {
                "ok": False,
                "error": "missing_ticker",
                "message": "ticker is required. Call search_catalog if you do not know it.",
            }
        limit_result = clamp_limit(limit, DEFAULT_ESTIMATE_LIMIT)
        if not limit_result["ok"]:
            return limit_result
        if not include_history and not include_latest_qtd:
            return {
                "ok": False,
                "error": "invalid_arguments",
                "message": "Set include_history and/or include_latest_qtd to true.",
            }

        company, suggestions = resolve_ticker(session, ticker)
        if company is None:
            return unknown_ticker_error(ticker, suggestions)

        kpi_result = resolve_kpi(session, company.ticker, kpi)
        if not kpi_result.get("ok"):
            return kpi_result
        resolved_kpi = kpi_result["kpi"]

        for field_name, raw in (("period_from", period_from), ("period_to", period_to)):
            parsed = parse_period(raw, field_name)
            if parsed is None:
                continue
            if not parsed["ok"]:
                return parsed

        period_from_n = parse_period(period_from, "period_from")
        period_to_n = parse_period(period_to, "period_to")
        start = period_from_n["period"] if period_from_n else None
        end = period_to_n["period"] if period_to_n else None

        filters = [KpiEstimate.ticker == company.ticker]
        if resolved_kpi:
            filters.append(KpiEstimate.kpi == resolved_kpi)

        history: list[dict[str, Any]] = []
        if include_history:
            stmt: Select[tuple[KpiEstimate]] = (
                select(KpiEstimate)
                .where(*filters, KpiEstimate.estimate_type == "historical")
                .order_by(KpiEstimate.kpi, KpiEstimate.period_start)
            )
            rows = session.execute(stmt).scalars().all()
            for row in rows:
                if start and period_tuple(row.period) < period_tuple(start):
                    continue
                if end and period_tuple(row.period) > period_tuple(end):
                    continue
                history.append(serialize_row(row))

        latest_qtd: list[dict[str, Any]] = []
        if include_latest_qtd:
            latest_qtd = self._latest_qtd_rows(
                session,
                ticker=company.ticker,
                kpi=resolved_kpi,
                period_from=start,
                period_to=end,
            )

        capped = limit_result["limit"]
        truncated = len(history) > capped
        history = history[:capped]
        return {
            "ok": True,
            "ticker": company.ticker,
            "company_name": company.company_name,
            "sector": company.sector,
            "kpi": resolved_kpi,
            "history": history,
            "latest_qtd": latest_qtd,
            "returned": len(history) + len(latest_qtd),
            "truncated": truncated,
            "note": (
                "latest_qtd is the most recent as_of snapshot per company/KPI/period. "
                "It is an intra-quarter estimate, not a completed quarter. "
                "In this sample the QTD period is 2026Q1 and the latest as_of is 2026-03-15. "
                "Use get_qtd_snapshots to inspect earlier dated snapshots. "
                "Do not annualize or extrapolate a full-quarter value unless you label that math explicitly."
            ),
        }

    def get_qtd_snapshots(
        self,
        session: Session,
        ticker: str,
        kpi: str | None = None,
        period: str | None = None,
        as_of: str | None = None,
        latest_only: bool = False,
        limit: int | None = None,
    ) -> dict[str, Any]:
        if not ticker or not ticker.strip():
            return {
                "ok": False,
                "error": "missing_ticker",
                "message": "ticker is required.",
            }
        limit_result = clamp_limit(limit, DEFAULT_QTD_LIMIT)
        if not limit_result["ok"]:
            return limit_result

        company, suggestions = resolve_ticker(session, ticker)
        if company is None:
            return unknown_ticker_error(ticker, suggestions)

        kpi_result = resolve_kpi(session, company.ticker, kpi)
        if not kpi_result.get("ok"):
            return kpi_result
        resolved_kpi = kpi_result["kpi"]

        parsed_period = parse_period(period, "period")
        if parsed_period is not None and not parsed_period["ok"]:
            return parsed_period
        resolved_period = parsed_period["period"] if parsed_period else None

        parsed_as_of = parse_iso_date(as_of, "as_of")
        if not parsed_as_of["ok"]:
            return parsed_as_of
        as_of_date: date | None = parsed_as_of["date"]

        filters = [
            KpiEstimate.ticker == company.ticker,
            KpiEstimate.estimate_type == "qtd",
        ]
        if resolved_kpi:
            filters.append(KpiEstimate.kpi == resolved_kpi)
        if resolved_period:
            filters.append(KpiEstimate.period == resolved_period)
        if as_of_date:
            filters.append(KpiEstimate.as_of == as_of_date)

        stmt = (
            select(KpiEstimate)
            .where(*filters)
            .order_by(KpiEstimate.kpi, KpiEstimate.period, KpiEstimate.as_of)
        )
        rows = list(session.execute(stmt).scalars().all())
        available_as_of = sorted(
            {
                value.isoformat()
                for value in session.execute(
                    select(KpiEstimate.as_of)
                    .where(
                        KpiEstimate.ticker == company.ticker,
                        KpiEstimate.estimate_type == "qtd",
                    )
                    .distinct()
                ).scalars()
                if value is not None
            }
        )

        if latest_only and not as_of_date:
            latest = self._latest_qtd_rows(
                session,
                ticker=company.ticker,
                kpi=resolved_kpi,
                period_from=resolved_period,
                period_to=resolved_period,
            )
            snapshots = latest
        else:
            snapshots = [serialize_row(row) for row in rows]

        capped = limit_result["limit"]
        truncated = len(snapshots) > capped
        snapshots = snapshots[:capped]

        if not snapshots:
            message = "No QTD snapshots matched those filters."
            if as_of_date:
                message += f" Available as_of dates: {', '.join(available_as_of) or 'none'}."
            return {
                "ok": True,
                "ticker": company.ticker,
                "company_name": company.company_name,
                "empty": True,
                "message": message,
                "available_as_of": available_as_of,
                "snapshots": [],
                "note": (
                    "QTD snapshots are dated intra-quarter estimates, not completed quarters."
                ),
            }

        return {
            "ok": True,
            "ticker": company.ticker,
            "company_name": company.company_name,
            "kpi": resolved_kpi,
            "period": resolved_period,
            "latest_only": latest_only,
            "snapshots": snapshots,
            "available_as_of": available_as_of,
            "returned": len(snapshots),
            "truncated": truncated,
            "note": (
                "Each snapshot is QTD as of its as_of date. Later snapshots replace earlier "
                "ones as the latest figure; they do not mean the quarter is finished. "
                "This sample's QTD window is 2026Q1, latest as_of 2026-03-15."
            ),
        }

    def latest_qtd_for(
        self,
        session: Session,
        ticker: str,
        kpi: str,
        period: str,
    ) -> KpiEstimate | None:
        stmt = (
            select(KpiEstimate)
            .where(
                KpiEstimate.ticker == ticker.upper(),
                KpiEstimate.kpi == kpi,
                KpiEstimate.period == period.upper(),
                KpiEstimate.estimate_type == "qtd",
            )
            .order_by(KpiEstimate.as_of.desc())
            .limit(1)
        )
        return session.execute(stmt).scalar_one_or_none()

    def _latest_qtd_rows(
        self,
        session: Session,
        *,
        ticker: str,
        kpi: str | None,
        period_from: str | None,
        period_to: str | None,
    ) -> list[dict[str, Any]]:
        filters = [
            KpiEstimate.ticker == ticker,
            KpiEstimate.estimate_type == "qtd",
        ]
        if kpi:
            filters.append(KpiEstimate.kpi == kpi)
        ranked = (
            select(
                KpiEstimate.id,
                func.row_number()
                .over(
                    partition_by=(
                        KpiEstimate.ticker,
                        KpiEstimate.kpi,
                        KpiEstimate.period,
                    ),
                    order_by=KpiEstimate.as_of.desc(),
                )
                .label("rn"),
            )
            .where(*filters)
            .subquery()
        )
        stmt = (
            select(KpiEstimate)
            .join(ranked, KpiEstimate.id == ranked.c.id)
            .where(ranked.c.rn == 1)
            .order_by(KpiEstimate.kpi, KpiEstimate.period)
        )
        rows = session.execute(stmt).scalars().all()
        payload = []
        for row in rows:
            if period_from and period_tuple(row.period) < period_tuple(period_from):
                continue
            if period_to and period_tuple(row.period) > period_tuple(period_to):
                continue
            payload.append(serialize_row(row))
        return payload
