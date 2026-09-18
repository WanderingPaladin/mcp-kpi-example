import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.models import KpiEstimate
from app.seed import seed_database
from tests.conftest import CSV_PATH


def test_import_loads_all_2000_records(session):
    count = session.execute(select(func.count()).select_from(KpiEstimate)).scalar_one()
    assert count == 2000


def test_import_is_repeatable(engine, session):
    seed_database(engine=engine, csv_path=CSV_PATH, reset=True)
    seed_database(engine=engine, csv_path=CSV_PATH, reset=True)
    count = session.execute(select(func.count()).select_from(KpiEstimate)).scalar_one()
    assert count == 2000


def test_historical_as_of_is_null_and_qtd_has_as_of(session):
    historical_with_as_of = session.execute(
        select(func.count())
        .select_from(KpiEstimate)
        .where(KpiEstimate.estimate_type == "historical", KpiEstimate.as_of.is_not(None))
    ).scalar_one()
    qtd_missing_as_of = session.execute(
        select(func.count())
        .select_from(KpiEstimate)
        .where(KpiEstimate.estimate_type == "qtd", KpiEstimate.as_of.is_(None))
    ).scalar_one()
    assert historical_with_as_of == 0
    assert qtd_missing_as_of == 0


def test_uniqueness_rejects_duplicate_historical_row(session):
    row = session.execute(
        select(KpiEstimate).where(KpiEstimate.estimate_type == "historical").limit(1)
    ).scalar_one()
    session.add(
        KpiEstimate(
            company_name=row.company_name,
            ticker=row.ticker,
            sector=row.sector,
            kpi=row.kpi,
            period_start=row.period_start,
            period_end=row.period_end,
            period=row.period,
            estimate_type="historical",
            value=row.value,
            unit=row.unit,
            as_of=None,
        )
    )
    with pytest.raises(IntegrityError):
        session.flush()
