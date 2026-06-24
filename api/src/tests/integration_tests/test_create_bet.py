"""Bet placement domain rules, exercised through client.queries.create_bet."""

from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from src.client.queries import ClientSideError, create_bet
from src.models import Bet, BetOutcome, FixtureResult, TransactionRecord, TransactionType
from src.tests.factories import make_fixture, make_user


def test_happy_path_debits_balance_and_records_transaction(db: Session) -> None:
    user = make_user(db, balance=Decimal("100.00"))
    fixture = make_fixture(db, status="NS", home_odds=Decimal("2.50"))

    result = create_bet(
        db,
        user=user,
        fixture_id=fixture.id,
        choice=FixtureResult.HOME,
        stake=Decimal("10.00"),
    )

    # returns = stake * odds + stake = 10 * 2.5 + 10
    assert result["returns"] == Decimal("35.00")

    db.refresh(user)
    assert user.balance == Decimal("90.00")

    bet = db.query(Bet).filter(Bet.id == result["id"]).one()
    assert bet.choice == FixtureResult.HOME.value
    assert bet.outcome == BetOutcome.UNDECIDED.value

    txn = (
        db.query(TransactionRecord)
        .filter(TransactionRecord.bet_id == bet.id)
        .one()
    )
    assert txn.type == TransactionType.BET.value
    assert txn.user_balance_before == Decimal("100.00")
    assert txn.user_balance_after == Decimal("90.00")


def test_insufficient_funds_rejected(db: Session) -> None:
    user = make_user(db, balance=Decimal("5.00"))
    fixture = make_fixture(db, status="NS")

    with pytest.raises(ClientSideError, match="Insufficient funds"):
        create_bet(
            db,
            user=user,
            fixture_id=fixture.id,
            choice=FixtureResult.HOME,
            stake=Decimal("10.00"),
        )

    db.refresh(user)
    assert user.balance == Decimal("5.00")
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
