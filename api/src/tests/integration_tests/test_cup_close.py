"""Cup close + settlement, through rapid_api.jobs.run_close_cups and the
internal_queries close primitives."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from src.client.cup import cups_won
from src.models import BetOutcome, CupStatus, FixtureResult
from src.rapid_api.internal_queries import fetch_cup_backstop_bets
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
    assert entry.final_rank == 1


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


def test_backstop_excludes_finished_but_unsettled_fixtures(db: Session) -> None:
    """A finished-but-unsettled bet (e.g. one left behind by the settle_bets row
    cap) must never be force-voided by the backstop — it belongs to the win/lose
    path. Only genuinely stuck (non-final) fixtures are voidable."""
    now = datetime.now(timezone.utc)
    start, end = _past_week()
    cup = make_cup(db, week_start=start, week_end=end, status=CupStatus.OPEN.value)
    user = make_user(db)
    entry = make_cup_entry(db, cup=cup, user=user)
    old = now - timedelta(hours=10)  # past the 6h backstop
    stuck = make_fixture(db, status="SUSP", kick_off=old)
    finished = make_fixture(db, status="FT", home_goals=2, away_goals=0, kick_off=old)
    stuck_bet = make_bet(db, user=user, fixture=stuck, cup_entry=entry)
    make_bet(db, user=user, fixture=finished, cup_entry=entry)

    voidable = {b.id for b in fetch_cup_backstop_bets(db, cup, now)}

    assert stuck_bet.id in voidable  # stuck fixture -> force-voidable
    assert len(voidable) == 1  # finished fixture excluded, not mispaid


def test_ties_produce_co_winners_and_cups_won_counts_them(db: Session) -> None:
    start, end = _past_week()
    cup = make_cup(db, week_start=start, week_end=end, status=CupStatus.OPEN.value)
    alice = make_user(db, email="a@test.com", auth_uid="a")
    bob = make_user(db, email="b@test.com", auth_uid="b")
    carol = make_user(db, email="c@test.com", auth_uid="c")
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
    assert a_entry.final_rank == 1
    assert b_entry.final_rank == 1  # co-winner on the tie
    assert c_entry.final_rank == 3  # two entries strictly ahead
    assert cup.final_entry_count == 3
    assert cups_won(db, alice) == 1
    assert cups_won(db, bob) == 1
    assert cups_won(db, carol) == 0


def test_settled_cup_is_not_reprocessed(db: Session) -> None:
    start, end = _past_week()
    cup = make_cup(db, week_start=start, week_end=end, status=CupStatus.SETTLED.value)
    user = make_user(db)
    entry = make_cup_entry(
        db, cup=cup, user=user, balance=Decimal("1000.00"), final_rank=1
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
    assert entry.final_rank == 1
