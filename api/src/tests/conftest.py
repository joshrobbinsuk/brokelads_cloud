import os

# database.py raises at import time if DATABASE_URL is unset. Tests run against
# their own in-memory SQLite engine (see the `db` fixture), so any value works.
os.environ.setdefault("DATABASE_URL", "sqlite://")

from typing import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from src import models  # noqa: F401  (registers tables on BaseModel.metadata)
from src.database import BaseModel


@pytest.fixture()
def db() -> Iterator[Session]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    BaseModel.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine, autocommit=False, autoflush=False)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()
