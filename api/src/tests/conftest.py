import os

# database.py raises at import time if DATABASE_URL is unset. Tests run against
# their own in-memory SQLite engine (see the `db` fixture), so any value works.
os.environ.setdefault("DATABASE_URL", "sqlite://")

from typing import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from src import models  # noqa: F401  (registers tables on BaseModel.metadata)
from src.database import BaseModel, get_db
from src.client.routes import router as client_router


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


@pytest.fixture()
def app(db: Session) -> FastAPI:
    test_app = FastAPI()
    test_app.include_router(client_router)
    test_app.dependency_overrides[get_db] = lambda: db
    return test_app


@pytest.fixture()
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client
