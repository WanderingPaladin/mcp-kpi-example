from app.services.kpi import KpiService

service = KpiService()


def test_historical_retrieval_for_completed_quarter(session):
    result = service.get_company_estimates(
        session,
        ticker="IGC",
        kpi="Total Revenue ($MM)",
        period_from="2022Q1",
        period_to="2022Q1",
        include_latest_qtd=False,
    )
    assert result["ok"] is True
    assert len(result["history"]) == 1
    row = result["history"][0]
    assert row["period"] == "2022Q1"
    assert row["estimate_type"] == "historical"
    assert row["as_of"] is None
    assert row["value"] == "519.63"
    assert row["unit"] == "$MM"


def test_history_range_excludes_qtd_unless_requested(session):
    result = service.get_company_estimates(
        session,
        ticker="IGC",
        kpi="Total Revenue ($MM)",
        period_from="2025Q4",
        period_to="2026Q1",
        include_history=True,
        include_latest_qtd=True,
    )
    periods = {row["period"] for row in result["history"]}
    assert periods == {"2025Q4"}
    assert result["latest_qtd"][0]["period"] == "2026Q1"
    assert result["latest_qtd"][0]["as_of"] == "2026-03-15"
