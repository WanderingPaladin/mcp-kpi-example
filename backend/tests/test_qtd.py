from datetime import date

from app.services.kpi import KpiService

service = KpiService()


def test_latest_qtd_is_march_15_2026(session):
    row = service.latest_qtd_for(session, "IGC", "Total Revenue ($MM)", "2026Q1")
    assert row is not None
    assert row.as_of == date(2026, 3, 15)
    assert str(row.value) == "627.45"
    assert row.unit == "$MM"
    assert row.period == "2026Q1"


def test_get_company_estimates_uses_latest_qtd_only(session):
    result = service.get_company_estimates(
        session,
        ticker="IGC",
        kpi="Total Revenue ($MM)",
        include_history=False,
        include_latest_qtd=True,
    )
    assert result["ok"] is True
    assert len(result["latest_qtd"]) == 1
    snapshot = result["latest_qtd"][0]
    assert snapshot["as_of"] == "2026-03-15"
    assert snapshot["period"] == "2026Q1"
    assert snapshot["value"] == "627.45"


def test_qtd_drilldown_returns_earlier_snapshots(session):
    result = service.get_qtd_snapshots(
        session,
        ticker="IGC",
        kpi="Total Revenue ($MM)",
        period="2026Q1",
    )
    as_of_dates = [item["as_of"] for item in result["snapshots"]]
    assert as_of_dates == ["2026-01-31", "2026-02-15", "2026-02-28", "2026-03-15"]
    assert result["snapshots"][0]["value"] == "263.09"


def test_qtd_latest_only_flag(session):
    result = service.get_qtd_snapshots(
        session,
        ticker="ACME",
        kpi="ASP ($)",
        latest_only=True,
    )
    assert len(result["snapshots"]) == 1
    assert result["snapshots"][0]["as_of"] == "2026-03-15"
    assert result["snapshots"][0]["value"] == "164.22"
