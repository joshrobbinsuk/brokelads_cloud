"""Contract tests for the cup-aware client surface: GET /client/cup/current,
GET /client/cup/{id}, GET /client/cups, and GET /client/me (cup balance +
cups_won). Money crosses the wire as strings."""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.client.routes import router as client_router
from src.client.utils.cognito import verify_token
from src.database import get_db
from src.models import Cup, CupStatus, User
from src.tests.factories import make_cup, make_cup_entry, make_user
from src.utils.weeks import current_week_window


@pytest.fixture()
def user(db: Session) -> User:
    return make_user(db, email="me@test.com", cognito_uuid="me")


@pytest.fixture()
def client(db: Session, user: User) -> Iterator[TestClient]:
    app = FastAPI()
    app.include_router(client_router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[verify_token] = lambda: {
        "sub": user.cognito_uuid,
        "email": user.email,
    }
    with TestClient(app) as test_client:
        yield test_client


def _current_cup(db: Session, status: str = CupStatus.OPEN.value) -> Cup:
    start, end = current_week_window(datetime.now(timezone.utc))
    return make_cup(db, week_start=start, week_end=end, status=status)


def test_me_falls_back_to_1000_and_zero_cups_won(client: TestClient) -> None:
    body = client.get("/client/me").json()
    assert body["balance"] == "1000"
    assert body["cups_won"] == 0
    assert body["avatar"] is None


def test_cup_current_shows_balance_rank_and_leaderboard(
    client: TestClient, db: Session, user: User
) -> None:
    cup = _current_cup(db)
    user.username = "me"
    user.avatar = "fox-red"
    other = make_user(
        db,
        email="rival@test.com",
        cognito_uuid="rival",
        username="rival",
        avatar="goat-teal",
    )
    make_cup_entry(db, cup=cup, user=other, balance=Decimal("1200.00"))
    make_cup_entry(db, cup=cup, user=user, balance=Decimal("900.00"))
    db.commit()

    body = client.get("/client/cup/current").json()

    assert body["cup"]["status"] == CupStatus.OPEN.value
    assert body["your_balance"] == "900.00"
    assert body["your_rank"] == 2
    assert [row["username"] for row in body["leaderboard"]] == ["rival", "me"]
    assert body["leaderboard"][0]["balance"] == "1200.00"
    assert body["leaderboard"][0]["avatar"] == "goat-teal"
    assert body["leaderboard"][1]["avatar"] == "fox-red"


def test_cup_current_when_no_cup_yet(client: TestClient) -> None:
    body = client.get("/client/cup/current").json()
    assert body["cup"] is None
    assert body["your_balance"] == "1000"
    assert body["your_rank"] is None
    assert body["leaderboard"] == []


def test_cup_by_id_and_404(client: TestClient, db: Session, user: User) -> None:
    cup = make_cup(db, status=CupStatus.SETTLED.value)
    make_cup_entry(db, cup=cup, user=user, balance=Decimal("1500.00"), final_rank=1)

    body = client.get(f"/client/cup/{cup.id}").json()
    assert body["cup"]["status"] == CupStatus.SETTLED.value
    assert body["leaderboard"][0]["is_winner"] is True

    assert client.get("/client/cup/does-not-exist").status_code == 404


def test_list_cups_most_recent_first(client: TestClient, db: Session) -> None:
    older = make_cup(db, week_start=datetime(2026, 1, 5, tzinfo=timezone.utc))
    newer = make_cup(db, week_start=datetime(2026, 1, 12, tzinfo=timezone.utc))

    body = client.get("/client/cups").json()
    assert [c["id"] for c in body["cups"]] == [newer.id, older.id]
