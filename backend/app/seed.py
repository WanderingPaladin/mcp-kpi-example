from __future__ import annotations

import csv
import logging
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from app.config import get_settings
from app.db import configure_engine, get_engine, init_db
from app.models import KpiEstimate

logger = logging.getLogger(__name__)


def parse_csv_date(raw: str | None):
    value = (raw or "").strip()
    if not value:
        return None
    return datetime.strptime(value, "%m/%d/%Y").date()


def load_csv_rows(csv_path: Path) -> list[KpiEstimate]:
    records: list[KpiEstimate] = []
    with csv_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for index, row in enumerate(reader, start=2):
            try:
                estimate_type = row["estimate_type"].strip().lower()
                as_of = parse_csv_date(row.get("as_of"))
                records.append(
                    KpiEstimate(
                        company_name=row["company_name"].strip(),
                        ticker=row["ticker"].strip().upper(),
                        sector=row["sector"].strip(),
                        kpi=row["kpi"].strip(),
                        period_start=parse_csv_date(row["period_start"]),
                        period_end=parse_csv_date(row["period_end"]),
                        period=row["period"].strip().upper(),
                        estimate_type=estimate_type,
                        value=Decimal(row["value"]),
                        unit=row["unit"].strip(),
                        as_of=as_of,
                    )
                )
            except (KeyError, ValueError, InvalidOperation) as exc:
                raise ValueError(f"Invalid CSV row {index}: {exc}") from exc
    if len(records) != 2000:
        raise ValueError(f"Expected 2000 CSV records, loaded {len(records)}")
    return records


def seed_database(
    engine: Engine | None = None,
    csv_path: Path | None = None,
    reset: bool = True,
) -> int:
    engine = engine or get_engine()
    init_db(engine)
    path = Path(csv_path or get_settings().csv_path)
    records = load_csv_rows(path)
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    with SessionLocal() as session:
        if reset:
            session.query(KpiEstimate).delete()
            session.flush()
        session.add_all(records)
        session.commit()
        count = session.query(KpiEstimate).count()
    logger.info("seeded_kpi_estimates", extra={"count": count, "csv_path": str(path)})
    return count


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    configure_engine()
    count = seed_database()
    print(f"Imported {count} KPI records from {get_settings().csv_path}")


if __name__ == "__main__":
    main()
