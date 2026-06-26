"""Helpers to persist test entities. Keep values to exact binary fractions
(.00/.25/.50/whole) so SQLite's float-backed NUMERIC stays exact."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from src.models import (
    Bet,
    BetOutcome,
    Fixture,
    FixtureResult,
    League,
    User,
    UserStatus,
)


def make_user(
    db: Session,
    *,
    balance: Decimal = Decimal("100.00"),
    email: str = "user@test.com",
    cognito_uuid: str = "cognito-1",
    status: str = UserStatus.ACTIVE.value,
) -> User:
    user = User(email=email, cognito_uuid=cognito_uuid, balance=balance, status=status)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def make_league(
    db: Session,
    *,
    rapid_api_id: int = 39,
    name: str = "Premier League",
    display_name: str | None = None,
    active: bool = True,
    logo: str | None = "league.png",
    country: str | None = "England",
    type: str | None = "League",
    last_fixture_fetch_at: datetime | None = None,
) -> League:
    league = League(
        rapid_api_id=rapid_api_id,
        name=name,
        display_name=display_name or name,
        active=active,
        logo=logo,
        country=country,
        type=type,
        last_fixture_fetch_at=last_fixture_fetch_at,
    )
    db.add(league)
    db.commit()
    db.refresh(league)
    return league


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
    league_id: str | None = None,
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
        league_id=league_id,
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
