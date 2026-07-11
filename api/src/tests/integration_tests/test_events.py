"""Domain-event emission from the mutation functions. Events are append-only and
observational; these tests assert they are written in the same transaction as the
mutation they describe."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from src.client.queries import create_bet, get_or_create_user
from src.models import Event, EventType, FixtureResult
from src.rapid_api.internal_queries import settle_bet, settle_cup
from src.tests.factories import make_cup, make_cup_entry, make_fixture, make_user
from src.utils.weeks import current_week_window


def _types(db: Session) -> list[str]:
    return [e.type for e in db.query(Event).all()]


def _kick_off_this_week() -> datetime:
    start, end = current_week_window(datetime.now(timezone.utc))
    candidate = datetime.now(timezone.utc) + timedelta(hours=1)
    return candidate if start <= candidate < end else start + timedelta(hours=1)


def test_user_creation_emits_user_created(db: Session) -> None:
    get_or_create_user(db, cognito_uuid="c1", email="a@test.com")
    assert EventType.USER_CREATED.value in _types(db)
    # Idempotent get on the second call emits nothing new.
    get_or_create_user(db, cognito_uuid="c1", email="a@test.com")
    assert _types(db).count(EventType.USER_CREATED.value) == 1


def test_bet_placement_emits_entry_created_and_bet_placed(db: Session) -> None:
    user = make_user(db)
    fixture = make_fixture(
        db, status="NS", home_odds=Decimal("2.50"), kick_off=_kick_off_this_week()
    )

    result = create_bet(
        db,
        user=user,
        fixture_id=fixture.id,
        choice=FixtureResult.HOME,
        stake=Decimal("10.00"),
    )

    types = _types(db)
    assert EventType.CUP_ENTRY_CREATED.value in types
    assert EventType.BET_PLACED.value in types
    placed = next(
        e for e in db.query(Event).all() if e.type == EventType.BET_PLACED.value
    )
    assert placed.user_id == user.id
    assert placed.payload["bet_id"] == result["id"]
    assert placed.payload["odds_struck"] == "2.50"
    assert placed.payload["stake"] == "10.00"


def test_settlement_emits_bet_settled(db: Session) -> None:
    user = make_user(db)
    cup = make_cup(db)
    entry = make_cup_entry(db, cup=cup, user=user, balance=Decimal("990.00"))
    fixture = make_fixture(db, status="FT", home_goals=2, away_goals=1)
    from src.tests.factories import make_bet

    bet = make_bet(
        db,
        user=user,
        fixture=fixture,
        cup_entry=entry,
        choice=FixtureResult.HOME,
        returns=Decimal("25.00"),
    )

    settle_bet(db, bet=bet, won=True)

    settled = next(
        e for e in db.query(Event).all() if e.type == EventType.BET_SETTLED.value
    )
    assert settled.payload["outcome"] == "WON"
    assert settled.payload["returns"] == "25.00"


def test_settle_cup_emits_one_event_per_entry(db: Session) -> None:
    cup = make_cup(db)
    alice = make_user(db, email="a@test.com", cognito_uuid="a")
    bob = make_user(db, email="b@test.com", cognito_uuid="b")
    make_cup_entry(db, cup=cup, user=alice, balance=Decimal("1200.00"))
    make_cup_entry(db, cup=cup, user=bob, balance=Decimal("800.00"))

    settle_cup(db, cup)

    settled = [
        e for e in db.query(Event).all() if e.type == EventType.CUP_SETTLED.value
    ]
    assert len(settled) == 2
    assert {e.payload["final_rank"] for e in settled} == {1, 2}
