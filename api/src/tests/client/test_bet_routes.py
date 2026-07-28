"""Wire contract for POST /client/bet rejections: a domain rejection serialises
`detail` as {"code", "message"} so the frontend branches on the code, never the
prose."""

from datetime import datetime, timedelta, timezone
from typing import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.client.queries import ClientErrorCode
from src.client.routes import router as client_router
from src.client.utils.firebase import verify_token
from src.database import get_db
from src.models import User
from src.tests.factories import make_fixture, make_user
from src.utils.weeks import current_week_window


@pytest.fixture()
def user(db: Session) -> User:
    return make_user(db, email="me@test.com", auth_uid="me")


@pytest.fixture()
def client(db: Session, user: User) -> Iterator[TestClient]:
    app = FastAPI()
    app.include_router(client_router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[verify_token] = lambda: {
        "sub": user.auth_uid,
        "email": user.email,
    }
    with TestClient(app) as test_client:
        yield test_client


def _kick_off_this_week() -> datetime:
    start, end = current_week_window(datetime.now(timezone.utc))
    candidate = datetime.now(timezone.utc) + timedelta(hours=1)
    if start <= candidate < end:
        return candidate
    return start + timedelta(hours=1)


def test_insufficient_funds_serialises_code_and_message(
    client: TestClient, db: Session
) -> None:
    fixture = make_fixture(db, status="NS", kick_off=_kick_off_this_week())

    resp = client.post(
        "/client/bet",
        json={"fixture_id": fixture.id, "choice": "HOME", "stake": 2000},
    )

    assert resp.status_code == 400
    assert resp.json()["detail"] == {
        "code": ClientErrorCode.INSUFFICIENT_FUNDS.value,
        "message": "Insufficient funds",
    }


def test_started_fixture_serialises_its_own_code(
    client: TestClient, db: Session
) -> None:
    fixture = make_fixture(db, status="FT", home_goals=1, away_goals=0)

    resp = client.post(
        "/client/bet",
        json={"fixture_id": fixture.id, "choice": "HOME", "stake": 10},
    )

    assert resp.status_code == 400
    assert resp.json()["detail"] == {
        "code": ClientErrorCode.FIXTURE_STARTED.value,
        "message": "Fixture has already started",
    }
