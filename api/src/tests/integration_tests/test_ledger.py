"""Ledger invariant and frozen-rank behaviour, exercised through the real bet,
settlement, and cup-close surfaces."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from src.client.cup import get_current_cup, leaderboard
from src.client.queries import create_bet
from src.models import (
    CupEntry,
    CupStatus,
    FixtureResult,
    LedgerEntry,
    LedgerEntryType,
)
from src.rapid_api.internal_queries import settle_cup
from src.rapid_api.jobs import run_settle_bets, run_settle_voided_bets
from src.settings import CUP_STARTING_STAKE
from src.tests.factories import make_cup, make_cup_entry, make_fixture, make_user
from src.utils.weeks import current_week_window


def _kick_off_this_week() -> datetime:
    start, end = current_week_window(datetime.now(timezone.utc))
    candidate = datetime.now(timezone.utc) + timedelta(hours=1)
    if start <= candidate < end:
        return candidate
    return start + timedelta(hours=1)


def test_entry_balance_equals_ledger_sum_across_win_lose_void(db: Session) -> None:
    user = make_user(db)
    kick_off = _kick_off_this_week()
    win_fx = make_fixture(db, status="NS", kick_off=kick_off)
    lose_fx = make_fixture(db, status="NS", kick_off=kick_off)
    void_fx = make_fixture(db, status="NS", kick_off=kick_off)

    for fixture in (win_fx, lose_fx, void_fx):
        create_bet(
            db,
            user=user,
            fixture_id=fixture.id,
            choice=FixtureResult.HOME,
            stake=Decimal("10.00"),
        )

    # Resolve the fixtures: home win, away win (bet loses), postponed (void).
    win_fx.status = "FT"
    win_fx.home_goals, win_fx.away_goals = 2, 0
    lose_fx.status = "FT"
    lose_fx.home_goals, lose_fx.away_goals = 0, 1
    void_fx.status = "PST"
    db.commit()

    run_settle_bets(db)
    run_settle_voided_bets(db)

    cup = get_current_cup(db, datetime.now(timezone.utc))
    assert cup is not None
    entry = (
        db.query(CupEntry)
        .filter(CupEntry.cup_id == cup.id, CupEntry.user_id == user.id)
        .one()
    )
    ledger = db.query(LedgerEntry).filter(LedgerEntry.cup_entry_id == entry.id).all()

    assert entry.balance == sum((e.amount for e in ledger), Decimal("0"))

    grants = [e for e in ledger if e.type == LedgerEntryType.ENTRY_GRANT.value]
    assert len(grants) == 1
    assert grants[0].amount == CUP_STARTING_STAKE


def _past_week() -> tuple[datetime, datetime]:
    end = datetime.now(timezone.utc) - timedelta(days=1)
    return end - timedelta(days=7), end


def test_frozen_ranks_survive_entry_deletion_with_a_gap(db: Session) -> None:
    start, end = _past_week()
    cup = make_cup(db, week_start=start, week_end=end, status=CupStatus.OPEN.value)
    users = [
        make_user(db, email=f"u{i}@test.com", auth_uid=f"c{i}", username=f"u{i}")
        for i in range(4)
    ]
    # Two tied at the top, then a clear third and fourth: ranks 1, 1, 3, 4.
    balances = [
        Decimal("1200.00"),
        Decimal("1200.00"),
        Decimal("1000.00"),
        Decimal("800.00"),
    ]
    entries = [
        make_cup_entry(db, cup=cup, user=u, balance=b) for u, b in zip(users, balances)
    ]

    settle_cup(db, cup)

    for e in entries:
        db.refresh(e)
    db.refresh(cup)
    assert [e.final_rank for e in entries] == [1, 1, 3, 4]
    assert cup.final_entry_count == 4

    # Remove the rank-3 entry; the frozen ranks must NOT renumber.
    db.delete(entries[2])
    db.commit()

    rows = leaderboard(db, cup)
    assert [row["rank"] for row in rows] == [1, 1, 4]
    assert [row["is_winner"] for row in rows] == [True, True, False]


def test_open_cup_leaderboard_ranks_live_by_balance(db: Session) -> None:
    cup = make_cup(db, status=CupStatus.OPEN.value)
    high = make_user(db, email="hi@test.com", auth_uid="hi", username="hi")
    low = make_user(db, email="lo@test.com", auth_uid="lo", username="lo")
    make_cup_entry(db, cup=cup, user=high, balance=Decimal("1200.00"))
    make_cup_entry(db, cup=cup, user=low, balance=Decimal("900.00"))

    rows = leaderboard(db, cup)

    assert [row["rank"] for row in rows] == [1, 2]
    assert [row["username"] for row in rows] == ["hi", "lo"]
    assert [row["is_winner"] for row in rows] == [False, False]
