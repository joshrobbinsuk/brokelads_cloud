"""Cup close + settlement, through rapid_api.jobs.run_close_cups and the
internal_queries close primitives."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from src.client.cup import cups_won
from src.models import BetOutcome, CupStatus, FixtureResult
from src.rapid_api.jobs import run_close_cups
from src.tests.factories import (
    make_bet,
    make_cup,
    make_cup_entry,
    make_fixture,
    make_user,
)


def _past_week() -> tuple[datetime, datetime]:
    end = datetime.now(timezone.utc) - timedelta(days=1)
    return end - timedelta(days=7), end


def test_backstop_force_voids_stuck_bet_and_settles(db: Session) -> None:
    start, end = _past_week()
    cup = make_cup(db, week_start=start, week_end=end, status=CupStatus.OPEN.value)
    user = make_user(db)
    entry = make_cup_entry(db, cup=cup, user=user, balance=Decimal("990.00"))
    # Stuck LIVE fixture kicked off well over the 6h backstop ago.
    fixture = make_fixture(
        db,
        status="LIVE",
        kick_off=datetime.now(timezone.utc) - timedelta(hours=10),
    )
    bet = make_bet(
        db, user=user, fixture=fixture, cup_entry=entry, stake=Decimal("10.00")
    )

    run_close_cups(db)

    db.refresh(bet)
    db.refresh(entry)
    db.refresh(cup)
    assert bet.outcome == BetOutcome.VOIDED.value
    assert entry.balance == Decimal("1000.00")  # stake refunded
    assert cup.status == CupStatus.SETTLED.value
    assert entry.is_winner is True


def test_cup_not_settled_while_undecided_bet_remains(db: Session) -> None:
    start, end = _past_week()
    cup = make_cup(db, week_start=start, week_end=end, status=CupStatus.OPEN.value)
    user = make_user(db)
    entry = make_cup_entry(db, cup=cup, user=user, balance=Decimal("990.00"))
    # Fixture kicked off only 2h ago — inside the backstop window, still LIVE.
    fixture = make_fixture(
        db,
        status="LIVE",
        kick_off=datetime.now(timezone.utc) - timedelta(hours=2),
    )
    bet = make_bet(db, user=user, fixture=fixture, cup_entry=entry)

    run_close_cups(db)

    db.refresh(bet)
    db.refresh(cup)
    assert bet.outcome == BetOutcome.UNDECIDED.value
    assert cup.status == CupStatus.CLOSING.value  # waits for settlement


def test_ties_produce_co_winners_and_cups_won_counts_them(db: Session) -> None:
    start, end = _past_week()
    cup = make_cup(db, week_start=start, week_end=end, status=CupStatus.OPEN.value)
    alice = make_user(db, email="a@test.com", cognito_uuid="a")
    bob = make_user(db, email="b@test.com", cognito_uuid="b")
    carol = make_user(db, email="c@test.com", cognito_uuid="c")
    a_entry = make_cup_entry(db, cup=cup, user=alice, balance=Decimal("1200.00"))
    b_entry = make_cup_entry(db, cup=cup, user=bob, balance=Decimal("1200.00"))
    c_entry = make_cup_entry(db, cup=cup, user=carol, balance=Decimal("800.00"))

    # No undecided bets -> settles immediately.
    run_close_cups(db)

    db.refresh(a_entry)
    db.refresh(b_entry)
    db.refresh(c_entry)
    db.refresh(cup)
    assert cup.status == CupStatus.SETTLED.value
    assert a_entry.is_winner is True
    assert b_entry.is_winner is True  # co-winner on the tie
    assert c_entry.is_winner is False
    assert cups_won(db, alice) == 1
    assert cups_won(db, bob) == 1
    assert cups_won(db, carol) == 0


def test_settled_cup_is_not_reprocessed(db: Session) -> None:
    start, end = _past_week()
    cup = make_cup(db, week_start=start, week_end=end, status=CupStatus.SETTLED.value)
    user = make_user(db)
    entry = make_cup_entry(
        db, cup=cup, user=user, balance=Decimal("1000.00"), is_winner=True
    )

    run_close_cups(db)  # SETTLED cups are skipped

    db.refresh(entry)
    assert entry.balance == Decimal("1000.00")


def test_won_bet_settles_cup_by_fixture_outcome(db: Session) -> None:
    start, end = _past_week()
    cup = make_cup(db, week_start=start, week_end=end, status=CupStatus.OPEN.value)
    user = make_user(db)
    entry = make_cup_entry(db, cup=cup, user=user, balance=Decimal("990.00"))
    fixture = make_fixture(
        db,
        status="FT",
        home_goals=2,
        away_goals=1,
        kick_off=datetime.now(timezone.utc) - timedelta(hours=2),
    )
    bet = make_bet(
        db,
        user=user,
        fixture=fixture,
        cup_entry=entry,
        choice=FixtureResult.HOME,
        returns=Decimal("35.00"),
    )

    run_close_cups(db)

    db.refresh(bet)
    db.refresh(entry)
    db.refresh(cup)
    # close_cups runs the normal settlement first, so the finished fixture is
    # won and the cup then terminates in the same pass.
    assert bet.outcome == BetOutcome.WON.value
    assert entry.balance == Decimal("1025.00")  # 990 + 35
    assert cup.status == CupStatus.SETTLED.value
    assert entry.is_winner is True
