import os
from collections.abc import Generator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")

from src.client.routes import router as client_router
from src.database import BaseModel as Base
from src.database import get_db


@pytest.fixture()
def engine():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    try:
        yield engine
    finally:
        Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def db(engine) -> Generator[Session, None, None]:
    session_local = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = session_local()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture()
def app(db: Session) -> FastAPI:
    test_app = FastAPI()
    test_app.include_router(client_router)

    def override_get_db():
        yield db

    test_app.dependency_overrides[get_db] = override_get_db
    return test_app


@pytest.fixture()
def client(app: FastAPI) -> Generator[TestClient, None, None]:
    with TestClient(app) as test_client:
        yield test_client
