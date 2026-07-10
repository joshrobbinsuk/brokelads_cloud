"""Bet placement domain rules, exercised through client.queries.create_bet.

Bets now debit a per-week CupEntry (created lazily on first bet), never
User.balance, and are only accepted for fixtures kicking off inside the current
cup's week window.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from src.client.cup import current_balance, get_current_cup
from src.client.queries import ClientSideError, create_bet
from src.models import (
    Bet,
    BetOutcome,
    CupEntry,
    FixtureResult,
    LedgerEntry,
    LedgerEntryType,
)
from src.settings import CUP_STARTING_STAKE
from src.tests.factories import make_fixture, make_user
from src.utils.weeks import current_week_window


def _kick_off_this_week() -> datetime:
    start, end = current_week_window(datetime.now(timezone.utc))
    now = datetime.now(timezone.utc)
    # A moment inside the current window that is still in the future so the
    # fixture reads as not-yet-kicked-off; fall back to just after start.
    candidate = now + timedelta(hours=1)
    if start <= candidate < end:
        return candidate
    return start + timedelta(hours=1)


def test_first_bet_creates_cup_and_entry_at_1000_and_debits(db: Session) -> None:
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

    # returns = stake * odds + stake = 10 * 2.5 + 10
    assert result["returns"] == Decimal("35.00")

    now = datetime.now(timezone.utc)
    cup = get_current_cup(db, now)
    assert cup is not None
    entry = (
        db.query(CupEntry)
        .filter(CupEntry.cup_id == cup.id, CupEntry.user_id == user.id)
        .one()
    )
    assert entry.balance == CUP_STARTING_STAKE - Decimal("10.00")

    bet = db.query(Bet).filter(Bet.id == result["id"]).one()
    assert bet.cup_entry_id == entry.id
    assert bet.outcome == BetOutcome.UNDECIDED.value

    grant = (
        db.query(LedgerEntry)
        .filter(
            LedgerEntry.cup_entry_id == entry.id,
            LedgerEntry.type == LedgerEntryType.ENTRY_GRANT.value,
        )
        .one()
    )
    assert grant.amount == CUP_STARTING_STAKE
    assert grant.balance_after == CUP_STARTING_STAKE
    assert grant.bet_id is None

    stake_entry = db.query(LedgerEntry).filter(LedgerEntry.bet_id == bet.id).one()
    assert stake_entry.type == LedgerEntryType.BET_STAKE.value
    assert stake_entry.amount == Decimal("-10.00")
    assert stake_entry.balance_after == CUP_STARTING_STAKE - Decimal("10.00")


def test_balance_read_falls_back_to_1000_with_no_entry(db: Session) -> None:
    user = make_user(db)
    assert current_balance(db, user, datetime.now(timezone.utc)) == CUP_STARTING_STAKE


def test_insufficient_funds_rejected(db: Session) -> None:
    user = make_user(db)
    fixture = make_fixture(db, status="NS", kick_off=_kick_off_this_week())

    with pytest.raises(ClientSideError, match="Insufficient funds"):
        create_bet(
            db,
            user=user,
            fixture_id=fixture.id,
            choice=FixtureResult.HOME,
            stake=Decimal("2000.00"),
        )

    assert db.query(Bet).count() == 0


def test_fixture_outside_current_window_rejected(db: Session) -> None:
    user = make_user(db)
    _, week_end = current_week_window(datetime.now(timezone.utc))
    fixture = make_fixture(db, status="NS", kick_off=week_end + timedelta(days=1))

    with pytest.raises(ClientSideError, match="outside this week"):
        create_bet(
            db,
            user=user,
            fixture_id=fixture.id,
            choice=FixtureResult.HOME,
            stake=Decimal("10.00"),
        )

    assert db.query(Bet).count() == 0


def test_started_fixture_rejected(db: Session) -> None:
    user = make_user(db)
    fixture = make_fixture(db, status="FT", home_goals=1, away_goals=0)

    with pytest.raises(ClientSideError, match="already started"):
        create_bet(
            db,
            user=user,
            fixture_id=fixture.id,
            choice=FixtureResult.HOME,
            stake=Decimal("10.00"),
        )


def test_fixture_without_odds_rejected(db: Session) -> None:
    user = make_user(db)
    fixture = make_fixture(db, status="NS", draw_odds=None)

    with pytest.raises(ClientSideError, match="does not have odds"):
        create_bet(
            db,
            user=user,
            fixture_id=fixture.id,
            choice=FixtureResult.HOME,
            stake=Decimal("10.00"),
        )


def test_unknown_fixture_rejected(db: Session) -> None:
    user = make_user(db)

    with pytest.raises(ClientSideError):
        create_bet(
            db,
            user=user,
            fixture_id="does-not-exist",
            choice=FixtureResult.HOME,
            stake=Decimal("10.00"),
        )
