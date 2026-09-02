"""The cron endpoint runs synchronously on the threadpool so a slow upstream
can't block the event loop for every other request."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.database import get_db
from src.rapid_api import routes as routes_module

CRON_KEY = "test-cron-key"


@pytest.fixture()
def cron_client(db: Session, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(routes_module, "CRON_AUTH_KEY", CRON_KEY)
    app = FastAPI()
    app.include_router(routes_module.router)
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app)


def test_runs_due_jobs(
    cron_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[Session] = []
    monkeypatch.setattr(routes_module, "run_jobs", calls.append)

    response = cron_client.post(
        "/rapid-api/run-jobs", headers={"X-Cron-Auth-Key": CRON_KEY}
    )

    assert response.status_code == 202
    assert len(calls) == 1


def test_wrong_key_is_rejected(
    cron_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def must_not_run(db: Session) -> None:
        raise AssertionError("jobs must not run without the cron key")

    monkeypatch.setattr(routes_module, "run_jobs", must_not_run)

    response = cron_client.post(
        "/rapid-api/run-jobs", headers={"X-Cron-Auth-Key": "wrong"}
    )

    assert response.status_code == 401
