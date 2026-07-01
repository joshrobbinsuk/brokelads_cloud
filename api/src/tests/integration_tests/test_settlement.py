"""Bet settlement, through internal_queries and the run_settle_bets job.

Settlement now moves the bet's CupEntry balance (win credits returns, void
refunds stake), never User.balance.
"""

from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from src.models import (
    BetOutcome,
    FixtureResult,
    TransactionRecord,
    TransactionType,
)
from src.rapid_api.internal_queries import settle_bet, settle_voided_bet
from src.rapid_api.jobs import run_settle_bets
from src.tests.factories import (
    make_bet,
    make_cup,
    make_cup_entry,
    make_fixture,
    make_user,
)


def test_won_bet_credits_cup_entry(db: Session) -> None:
    user = make_user(db)
    cup = make_cup(db)
    entry = make_cup_entry(db, cup=cup, user=user, balance=Decimal("990.00"))
    fixture = make_fixture(db, status="FT", home_goals=2, away_goals=1)
    bet = make_bet(
        db,
        user=user,
        fixture=fixture,
        cup_entry=entry,
        choice=FixtureResult.HOME,
        returns=Decimal("35.00"),
    )

    settle_bet(db, bet=bet, won=True)

    db.refresh(bet)
    db.refresh(entry)
    assert bet.outcome == BetOutcome.WON.value
    assert entry.balance == Decimal("1025.00")  # 990 + 35
    txn = db.query(TransactionRecord).filter(TransactionRecord.bet_id == bet.id).one()
    assert txn.type == TransactionType.PAYOUT_BET_WON.value
    assert txn.user_balance_after == Decimal("1025.00")


def test_lost_bet_pays_nothing(db: Session) -> None:
    user = make_user(db)
    cup = make_cup(db)
    entry = make_cup_entry(db, cup=cup, user=user, balance=Decimal("990.00"))
    fixture = make_fixture(db, status="FT", home_goals=0, away_goals=1)
    bet = make_bet(
        db, user=user, fixture=fixture, cup_entry=entry, choice=FixtureResult.HOME
    )

    settle_bet(db, bet=bet, won=False)

    db.refresh(bet)
    db.refresh(entry)
    assert bet.outcome == BetOutcome.LOST.value
    assert entry.balance == Decimal("990.00")
    assert db.query(TransactionRecord).count() == 0


def test_settling_twice_raises(db: Session) -> None:
    user = make_user(db)
    cup = make_cup(db)
    entry = make_cup_entry(db, cup=cup, user=user)
    fixture = make_fixture(db, status="FT", home_goals=2, away_goals=1)
    bet = make_bet(
        db,
        user=user,
        fixture=fixture,
        cup_entry=entry,
        choice=FixtureResult.HOME,
        outcome=BetOutcome.WON.value,
    )

    with pytest.raises(Exception, match="already been settled"):
        settle_bet(db, bet=bet, won=True)


def test_voided_bet_refunds_stake(db: Session) -> None:
    user = make_user(db)
    cup = make_cup(db)
    entry = make_cup_entry(db, cup=cup, user=user, balance=Decimal("990.00"))
    fixture = make_fixture(db, status="PST")
    bet = make_bet(
        db,
        user=user,
        fixture=fixture,
        cup_entry=entry,
        choice=FixtureResult.HOME,
        stake=Decimal("10.00"),
    )

    settle_voided_bet(db, bet=bet)

    db.refresh(bet)
    db.refresh(entry)
    assert bet.outcome == BetOutcome.VOIDED.value
    assert entry.balance == Decimal("1000.00")  # stake refunded
    txn = db.query(TransactionRecord).filter(TransactionRecord.bet_id == bet.id).one()
    assert txn.type == TransactionType.PAYOUT_BET_VOIDED.value


def test_run_settle_bets_settles_by_fixture_outcome(db: Session) -> None:
    # Home win 2-1: the HOME bet wins, the AWAY bet loses.
    cup = make_cup(db)
    fixture = make_fixture(db, status="FT", home_goals=2, away_goals=1)
    winner = make_user(db, email="w@test.com", cognito_uuid="w")
    loser = make_user(db, email="l@test.com", cognito_uuid="l")
    winner_entry = make_cup_entry(db, cup=cup, user=winner, balance=Decimal("990.00"))
    loser_entry = make_cup_entry(db, cup=cup, user=loser, balance=Decimal("990.00"))
    won_bet = make_bet(
        db,
        user=winner,
        fixture=fixture,
        cup_entry=winner_entry,
        choice=FixtureResult.HOME,
        returns=Decimal("35.00"),
    )
    lost_bet = make_bet(
        db,
        user=loser,
        fixture=fixture,
        cup_entry=loser_entry,
        choice=FixtureResult.AWAY,
        returns=Decimal("40.00"),
    )

    run_settle_bets(db)

    db.refresh(won_bet)
    db.refresh(lost_bet)
    db.refresh(winner_entry)
    db.refresh(loser_entry)
    assert won_bet.outcome == BetOutcome.WON.value
    assert lost_bet.outcome == BetOutcome.LOST.value
    assert winner_entry.balance == Decimal("1025.00")
    assert loser_entry.balance == Decimal("990.00")
