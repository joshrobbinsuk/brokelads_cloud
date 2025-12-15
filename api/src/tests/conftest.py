import json
import os
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from ..main import app
from ..database import get_db, BaseModel as Base


@pytest.fixture(scope="session")
def engine():
    return create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )


@pytest.fixture(scope="session", autouse=True)
def schema(engine):
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def db(engine):
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture()
def client(db):
    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def rapid_api_fixtures_payload():
    path = os.path.join(
        os.path.dirname(__file__), "fixtures", "rapid_api_fixtures.json"
    )
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


class DummyResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests

            raise requests.HTTPError(f"{self.status_code} error")


@pytest.fixture()
def mock_requests_get(monkeypatch, rapid_api_fixtures_payload):
    import src.rapid_api.external_calls as external_calls

    def _mock_get(url, headers=None, **kwargs):
        return DummyResponse(rapid_api_fixtures_payload, status_code=200)

    monkeypatch.setattr(external_calls.requests, "get", _mock_get)
    return _mock_get
