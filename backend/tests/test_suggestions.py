from app.services.kpi import KpiService

service = KpiService()


def test_unknown_ticker_returns_suggestions(session):
    result = service.get_company_estimates(session, ticker="IGCC")
    assert result["ok"] is False
    assert result["error"] == "unknown_ticker"
    tickers = [item["ticker"] for item in result["suggestions"]]
    assert "IGC" in tickers


def test_company_name_resolves_to_ticker(session):
    result = service.search_catalog(session, query="Imaginary Streaming")
    assert result["ok"] is True
    assert any(company["ticker"] == "IGC" for company in result["companies"])


def test_unknown_kpi_returns_suggestions(session):
    result = service.get_company_estimates(session, ticker="IGC", kpi="gross margin")
    assert result["ok"] is False
    assert result["error"] == "unknown_kpi"
    assert "Total Revenue ($MM)" in result["available_kpis"]
    assert result["message"]


def test_ambiguous_subscribers_does_not_auto_pick(session):
    result = service.get_company_estimates(session, ticker="IGC", kpi="subscribers")
    assert result["ok"] is False
    assert result["error"] == "unknown_kpi"
    assert "Global Net Added Subscribers" in result["suggestions"]
    assert "U.S. Net Added Subscribers" in result["suggestions"]


def test_invalid_period_is_recoverable(session):
    result = service.get_company_estimates(session, ticker="IGC", period_from="Q1-2026")
    assert result["ok"] is False
    assert result["error"] == "invalid_period"


def test_unknown_sector_suggestions(session):
    result = service.search_catalog(session, sector="Softwear")
    assert result["ok"] is False
    assert result["error"] == "unknown_sector"
    assert "Software" in result["suggestions"]
