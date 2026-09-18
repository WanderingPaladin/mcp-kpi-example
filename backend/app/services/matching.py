from __future__ import annotations

import difflib
import re
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import KpiEstimate

_NON_ALNUM = re.compile(r"[^a-z0-9]+")

KPI_ALIASES: dict[str, list[str]] = {
    "revenue": ["Total Revenue ($MM)"],
    "total revenue": ["Total Revenue ($MM)"],
    "sales": ["Total Revenue ($MM)"],
    "asp": ["ASP ($)"],
    "average selling price": ["ASP ($)"],
    "units": ["Units Sold"],
    "units sold": ["Units Sold"],
    "subscribers": ["Global Net Added Subscribers", "U.S. Net Added Subscribers"],
    "global subscribers": ["Global Net Added Subscribers"],
    "us subscribers": ["U.S. Net Added Subscribers"],
    "u.s. subscribers": ["U.S. Net Added Subscribers"],
    "net added subscribers": ["Global Net Added Subscribers", "U.S. Net Added Subscribers"],
    "subscriber growth": ["Global Net Added Subscribers", "U.S. Net Added Subscribers"],
}


def normalize(text: str) -> str:
    return _NON_ALNUM.sub(" ", text.lower()).strip()


@dataclass(frozen=True)
class CompanyRef:
    ticker: str
    company_name: str
    sector: str


def list_companies(session: Session) -> list[CompanyRef]:
    rows = session.execute(
        select(
            KpiEstimate.ticker,
            KpiEstimate.company_name,
            KpiEstimate.sector,
        ).distinct()
    ).all()
    return [
        CompanyRef(ticker=row.ticker, company_name=row.company_name, sector=row.sector)
        for row in rows
    ]


def list_kpis_for_ticker(session: Session, ticker: str) -> list[str]:
    rows = session.execute(
        select(KpiEstimate.kpi)
        .where(KpiEstimate.ticker == ticker.upper())
        .distinct()
        .order_by(KpiEstimate.kpi)
    ).scalars()
    return list(rows)


def suggest_tickers(
    companies: list[CompanyRef],
    query: str,
    *,
    limit: int = 5,
) -> list[CompanyRef]:
    needle = normalize(query)
    if not needle:
        return []

    scored: list[tuple[float, CompanyRef]] = []
    for company in companies:
        ticker_n = normalize(company.ticker)
        name_n = normalize(company.company_name)
        score = 0.0
        if needle == ticker_n or needle == name_n:
            score = 1.0
        elif needle in ticker_n or needle in name_n:
            score = 0.92
        else:
            score = max(
                difflib.SequenceMatcher(None, needle, ticker_n).ratio(),
                difflib.SequenceMatcher(None, needle, name_n).ratio(),
            )
        if score >= 0.55:
            scored.append((score, company))
    scored.sort(key=lambda item: (-item[0], item[1].ticker))
    deduped: list[CompanyRef] = []
    seen: set[str] = set()
    for _, company in scored:
        if company.ticker in seen:
            continue
        seen.add(company.ticker)
        deduped.append(company)
        if len(deduped) >= limit:
            break
    return deduped


def suggest_kpis(available: list[str], query: str, *, limit: int = 5) -> list[str]:
    needle = normalize(query)
    if not needle:
        return []

    alias_hits = KPI_ALIASES.get(needle, [])
    ranked: list[tuple[float, str]] = []
    for kpi in available:
        kpi_n = normalize(kpi)
        score = 0.0
        if kpi in alias_hits or needle == kpi_n:
            score = 1.0
        elif needle in kpi_n:
            score = 0.9
        else:
            score = difflib.SequenceMatcher(None, needle, kpi_n).ratio()
            if kpi in alias_hits:
                score = max(score, 0.95)
        if score >= 0.5:
            ranked.append((score, kpi))
    ranked.sort(key=lambda item: (-item[0], item[1]))
    result: list[str] = []
    for _, kpi in ranked:
        if kpi not in result:
            result.append(kpi)
        if len(result) >= limit:
            break
    for alias_kpi in alias_hits:
        if alias_kpi in available and alias_kpi not in result:
            result.append(alias_kpi)
    return result[:limit]


def resolve_ticker(session: Session, ticker: str) -> tuple[CompanyRef | None, list[CompanyRef]]:
    companies = list_companies(session)
    raw = ticker.strip()
    upper = raw.upper()
    exact = next((company for company in companies if company.ticker == upper), None)
    if exact:
        return exact, []

    name_exact = next(
        (company for company in companies if company.company_name.lower() == raw.lower()),
        None,
    )
    if name_exact:
        return name_exact, []

    unique_name = [
        company
        for company in companies
        if normalize(raw) and normalize(raw) in normalize(company.company_name)
    ]
    if len(unique_name) == 1:
        return unique_name[0], []

    suggestions = suggest_tickers(companies, raw)
    if not suggestions:
        suggestions = sorted(companies, key=lambda item: item.ticker)[:5]
    return None, suggestions
