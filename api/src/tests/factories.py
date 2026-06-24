"""Helpers to persist test entities. Keep values to exact binary fractions
(.00/.25/.50/whole) so SQLite's float-backed NUMERIC stays exact."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from src.models import Bet, BetOutcome, Fixture, FixtureResult, User, UserStatus


def make_user(
    db: Session,
    *,
    balance: Decimal = Decimal("100.00"),
    email: str = "user@test.com",
    cognito_uuid: str = "cognito-1",
    status: str = UserStatus.ACTIVE.value,
) -> User:
    user = User(
        email=email, cognito_uuid=cognito_uuid, balance=balance, status=status
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def make_fixture(
    db: Session,
    *,
    status: str = "NS",
    home_odds: Decimal | None = Decimal("2.00"),
    away_odds: Decimal | None = Decimal("3.00"),
    draw_odds: Decimal | None = Decimal("3.50"),
    home_goals: int | None = None,
    away_goals: int | None = None,
    kick_off: datetime | None = None,
) -> Fixture:
    fixture = Fixture(
        status=status,
        rapid_api_id=1,
        kick_off=kick_off or datetime.now(timezone.utc) + timedelta(days=1),
        venue="Stadium",
        home_team="Home FC",
        home_team_logo="home.png",
        away_team="Away FC",
        away_team_logo="away.png",
        home_odds=home_odds,
        away_odds=away_odds,
        draw_odds=draw_odds,
        home_goals=home_goals,
        away_goals=away_goals,
    )
    db.add(fixture)
    db.commit()
    db.refresh(fixture)
    return fixture


def make_bet(
    db: Session,
    *,
    user: User,
    fixture: Fixture,
    choice: FixtureResult = FixtureResult.HOME,
    stake: Decimal = Decimal("10.00"),
    returns: Decimal = Decimal("30.00"),
    outcome: str = BetOutcome.UNDECIDED.value,
) -> Bet:
    bet = Bet(
        user_id=user.id,
        fixture_id=fixture.id,
        choice=choice.value,
        stake=stake,
        returns=returns,
        outcome=outcome,
    )
    db.add(bet)
    db.commit()
    db.refresh(bet)
    return bet
