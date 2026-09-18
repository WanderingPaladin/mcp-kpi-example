from datetime import date
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, Index, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class KpiEstimate(Base):
    """One published estimate snapshot.

    Historical rows have a null as_of (the figure is for a completed fiscal quarter).
    QTD rows always have as_of (the intra-quarter snapshot date). Uniqueness treats
    those null as_of values as equal so a company/KPI/period cannot be stored twice.
    """

    __tablename__ = "kpi_estimates"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_name: Mapped[str] = mapped_column(String(200), nullable=False)
    ticker: Mapped[str] = mapped_column(String(16), nullable=False)
    sector: Mapped[str] = mapped_column(String(80), nullable=False)
    kpi: Mapped[str] = mapped_column(String(120), nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    period: Mapped[str] = mapped_column(String(8), nullable=False)
    estimate_type: Mapped[str] = mapped_column(String(16), nullable=False)
    value: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    unit: Mapped[str] = mapped_column(String(16), nullable=False)
    as_of: Mapped[date | None] = mapped_column(Date, nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "ticker",
            "kpi",
            "period",
            "estimate_type",
            "as_of",
            name="uq_kpi_estimate_natural_key",
            postgresql_nulls_not_distinct=True,
        ),
        CheckConstraint(
            "estimate_type IN ('historical', 'qtd')",
            name="ck_kpi_estimate_type",
        ),
        CheckConstraint(
            "(estimate_type = 'historical' AND as_of IS NULL) OR "
            "(estimate_type = 'qtd' AND as_of IS NOT NULL)",
            name="ck_kpi_as_of_matches_type",
        ),
        Index("ix_kpi_ticker", "ticker"),
        Index("ix_kpi_ticker_kpi_period", "ticker", "kpi", "period"),
        Index("ix_kpi_sector", "sector"),
        Index("ix_kpi_qtd_as_of", "estimate_type", "as_of"),
    )
