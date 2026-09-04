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
from src.client.utils.firebase import verify_token
from src.database import get_db
from src.models import (
    BetOutcome,
    Cup,
    CupStatus,
    LedgerEntry,
    LedgerEntryType,
    User,
)
from src.tests.factories import (
    make_bet,
    make_cup,
    make_cup_entry,
    make_fixture,
    make_user,
)
from src.settings import CUP_STARTING_STAKE
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


def _current_cup(db: Session, status: str = CupStatus.OPEN.value) -> Cup:
    start, end = current_week_window(datetime.now(timezone.utc))
    return make_cup(db, week_start=start, week_end=end, status=status)


def test_me_falls_back_to_1000_and_zero_cups_won(client: TestClient) -> None:
    body = client.get("/client/me").json()
    assert body["balance"] == "1000"
    assert body["cups_won"] == 0
    # Wire contract: streak fields are always present, ints, zero for a fresh user.
    assert body["participation_streak"] == 0
    assert body["profit_streak"] == 0


def test_cup_current_shows_balance_rank_and_leaderboard(
    client: TestClient, db: Session, user: User
) -> None:
    cup = _current_cup(db)
    user.username = "me"
    other = make_user(
        db,
        email="rival@test.com",
        auth_uid="rival",
        username="rival",
    )
    rival_entry = make_cup_entry(db, cup=cup, user=other, balance=Decimal("1200.00"))
    make_cup_entry(db, cup=cup, user=user, balance=Decimal("900.00"))
    fixture = make_fixture(db)
    # Only open bets count towards potential — settled ones are already in balance.
    make_bet(
        db, user=other, fixture=fixture, cup_entry=rival_entry, returns=Decimal("30.00")
    )
    make_bet(
        db, user=other, fixture=fixture, cup_entry=rival_entry, returns=Decimal("12.50")
    )
    make_bet(
        db,
        user=other,
        fixture=fixture,
        cup_entry=rival_entry,
        returns=Decimal("500.00"),
        outcome=BetOutcome.WON.value,
    )
    db.commit()

    body = client.get("/client/cup/current").json()

    assert body["cup"]["status"] == CupStatus.OPEN.value
    assert body["your_balance"] == "900.00"
    assert body["your_rank"] == 2
    assert [row["username"] for row in body["leaderboard"]] == ["rival", "me"]
    assert body["leaderboard"][0]["balance"] == "1200.00"
    # potential = balance + returns of every still-open bet (best-case week end).
    assert body["leaderboard"][0]["potential"] == "1242.50"
    assert body["leaderboard"][1]["potential"] == "900.00"
    # Wire contract: every leaderboard row carries both streak fields as ints.
    assert body["leaderboard"][0]["participation_streak"] == 0
    assert body["leaderboard"][0]["profit_streak"] == 0


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


def test_best_weeks_ranks_settled_pots_raw(
    client: TestClient, db: Session, user: User
) -> None:
    rival = make_user(db, email="rival@test.com", auth_uid="rival", username="rival")
    week_a = make_cup(
        db,
        week_start=datetime(2026, 1, 5, tzinfo=timezone.utc),
        status=CupStatus.SETTLED.value,
    )
    week_b = make_cup(
        db,
        week_start=datetime(2026, 1, 12, tzinfo=timezone.utc),
        status=CupStatus.SETTLED.value,
    )
    make_cup_entry(db, cup=week_a, user=user, balance=Decimal("1500.00"), final_rank=1)
    make_cup_entry(db, cup=week_b, user=user, balance=Decimal("1200.00"), final_rank=2)
    make_cup_entry(db, cup=week_a, user=rival, balance=Decimal("900.00"), final_rank=2)
    make_cup_entry(db, cup=week_b, user=rival, balance=Decimal("1300.00"), final_rank=1)
    # An open cup's pot is not frozen yet, however big.
    make_cup_entry(db, cup=_current_cup(db), user=rival, balance=Decimal("9999.00"))

    body = client.get("/client/cups/all-time").json()

    assert [(e["rank"], e["user_id"], e["balance"]) for e in body["best_weeks"]] == [
        (1, user.id, "1500.00"),
        (2, rival.id, "1300.00"),
        (3, user.id, "1200.00"),
        (4, rival.id, "900.00"),
    ]
    top = body["best_weeks"][0]
    assert top["cup_id"] == week_a.id
    assert top["week_start"].startswith("2026-01-05")
    assert body["best_weeks"][1]["username"] == "rival"


def test_best_weeks_is_capped_at_five(client: TestClient, db: Session) -> None:
    cup = make_cup(db, status=CupStatus.SETTLED.value)
    for i in range(7):
        punter = make_user(db, email=f"u{i}@test.com", auth_uid=f"u{i}")
        make_cup_entry(db, cup=cup, user=punter, balance=Decimal(f"{1000 + i}.00"))

    entries = client.get("/client/cups/all-time").json()["best_weeks"]

    assert [e["balance"] for e in entries] == [
        "1006.00",
        "1005.00",
        "1004.00",
        "1003.00",
        "1002.00",
    ]


def test_me_best_week_is_the_biggest_settled_pot(
    client: TestClient, db: Session, user: User
) -> None:
    assert client.get("/client/me").json()["best_week"] is None

    week_a = make_cup(
        db,
        week_start=datetime(2026, 1, 5, tzinfo=timezone.utc),
        status=CupStatus.SETTLED.value,
    )
    week_b = make_cup(
        db,
        week_start=datetime(2026, 1, 12, tzinfo=timezone.utc),
        status=CupStatus.SETTLED.value,
    )
    make_cup_entry(db, cup=week_a, user=user, balance=Decimal("1100.00"))
    make_cup_entry(db, cup=week_b, user=user, balance=Decimal("1400.00"))
    make_cup_entry(db, cup=_current_cup(db), user=user, balance=Decimal("5000.00"))

    best = client.get("/client/me").json()["best_week"]

    assert best["balance"] == "1400.00"
    assert best["week_start"].startswith("2026-01-12")


def test_best_weeks_equal_pots_share_a_rank_and_a_tie_is_never_split(
    client: TestClient, db: Session
) -> None:
    cup = make_cup(db, status=CupStatus.SETTLED.value)
    for i, balance in enumerate(
        ["1500", "1500", "1400", "1300", "1200", "1200", "1100"]
    ):
        punter = make_user(db, email=f"u{i}@test.com", auth_uid=f"u{i}")
        make_cup_entry(db, cup=cup, user=punter, balance=Decimal(f"{balance}.00"))

    entries = client.get("/client/cups/all-time").json()["best_weeks"]

    assert [(e["rank"], e["balance"]) for e in entries] == [
        (1, "1500.00"),
        (1, "1500.00"),
        (3, "1400.00"),
        (4, "1300.00"),
        (5, "1200.00"),
        (5, "1200.00"),
    ]


def _settled_profit_week(
    db: Session, user: User, week_start: datetime, balance: str
) -> None:
    cup = make_cup(db, week_start=week_start, status=CupStatus.SETTLED.value)
    entry = make_cup_entry(db, cup=cup, user=user, balance=Decimal(balance))
    db.add(
        LedgerEntry(
            cup_entry_id=entry.id,
            type=LedgerEntryType.ENTRY_GRANT.value,
            amount=CUP_STARTING_STAKE,
            balance_after=CUP_STARTING_STAKE,
            bet_id=None,
        )
    )
    db.commit()


def test_all_time_profit_streak_record_on_the_wire(
    client: TestClient, db: Session, user: User
) -> None:
    assert client.get("/client/cups/all-time").json()["profit_streak_record"] is None

    weeks = [
        datetime(2026, 1, 5, tzinfo=timezone.utc),
        datetime(2026, 1, 12, tzinfo=timezone.utc),
    ]
    for week in weeks:
        _settled_profit_week(db, user, week, "1100.00")

    record = client.get("/client/cups/all-time").json()["profit_streak_record"]

    assert record["length"] == 2
    assert [(h["user_id"], h["is_current"]) for h in record["holders"]] == [
        (user.id, True)
    ]
    assert record["holders"][0]["ended_week_start"].startswith("2026-01-12")
