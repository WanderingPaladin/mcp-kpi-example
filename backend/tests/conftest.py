from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy.orm import Session, sessionmaker

from app.config import REPO_ROOT, get_settings
from app.db import configure_engine, init_db
from app.models import Base
from app.seed import seed_database

CSV_PATH = REPO_ROOT / "data" / "kpi_sample_2000.csv"


@pytest.fixture(scope="session")
def engine():
    get_settings.cache_clear()
    eng = configure_engine(get_settings().database_url)
    Base.metadata.drop_all(eng)
    init_db(eng)
    seed_database(engine=eng, csv_path=CSV_PATH, reset=True)
    yield eng


@pytest.fixture
def session(engine) -> Session:
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    with SessionLocal() as db_session:
        yield db_session
        db_session.rollback()
