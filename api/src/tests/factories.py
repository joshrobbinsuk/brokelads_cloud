"""Helpers to persist test entities. Keep values to exact binary fractions
(.00/.25/.50/whole) so SQLite's float-backed NUMERIC stays exact."""

import itertools
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from src.models import (
    Bet,
    BetOutcome,
    Cup,
    CupEntry,
    CupStatus,
    Fixture,
    FixtureResult,
    League,
    User,
    UserStatus,
)

# fixture.rapid_api_id is now uniquely indexed, so each fixture needs a distinct
# one; tests that care about the exact value pass it explicitly.
_rapid_api_id_seq = itertools.count(1)

VALID_SHIRT: dict[str, object] = {
    "background": "teal",
    "body": "red",
    "pattern": "stripes",
    "pattern_colour": "white",
    "motif": "fox",
}
NULL_MOTIF_SHIRT: dict[str, object] = {
    "background": "gold",
    "body": "blue",
    "pattern": "hoops",
    "pattern_colour": "white",
    "motif": None,
}


def make_user(
    db: Session,
    *,
    email: str = "user@test.com",
    auth_uid: str = "auth-1",
    status: str = UserStatus.ACTIVE.value,
    username: str | None = None,
    shirt: dict[str, object] | None = None,
) -> User:
    user = User(
        email=email,
        auth_uid=auth_uid,
        status=status,
        username=username,
        shirt=shirt,
    )
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
) -> League:
    league = League(
        rapid_api_id=rapid_api_id,
        name=name,
        display_name=display_name or name,
        active=active,
        logo=logo,
        country=country,
        type=type,
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
    rapid_api_id: int | None = None,
) -> Fixture:
    fixture = Fixture(
        status=status,
        rapid_api_id=(
            rapid_api_id if rapid_api_id is not None else next(_rapid_api_id_seq)
        ),
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


_DEFAULT_CUP_WEEK_START = datetime(2020, 1, 6, 0, 0, tzinfo=timezone.utc)


def _default_cup_entry(db: Session, user: User) -> CupEntry:
    """A cup entry for tests that need a bet but don't care about the cup — every
    bet now carries a NOT NULL cup_entry_id. Shared across such bets via a fixed
    week_start that won't collide with cups a test builds explicitly."""
    cup = db.query(Cup).filter(Cup.week_start == _DEFAULT_CUP_WEEK_START).first()
    if cup is None:
        cup = make_cup(db, week_start=_DEFAULT_CUP_WEEK_START)
    entry = (
        db.query(CupEntry)
        .filter(CupEntry.cup_id == cup.id, CupEntry.user_id == user.id)
        .first()
    )
    if entry is None:
        entry = make_cup_entry(db, cup=cup, user=user)
    return entry


def make_bet(
    db: Session,
    *,
    user: User,
    fixture: Fixture,
    choice: FixtureResult = FixtureResult.HOME,
    stake: Decimal = Decimal("10.00"),
    returns: Decimal = Decimal("30.00"),
    outcome: str = BetOutcome.UNDECIDED.value,
    cup_entry: "CupEntry | None" = None,
) -> Bet:
    if cup_entry is None:
        cup_entry = _default_cup_entry(db, user)
    bet = Bet(
        user_id=user.id,
        fixture_id=fixture.id,
        cup_entry_id=cup_entry.id,
        choice=choice.value,
        stake=stake,
        returns=returns,
        outcome=outcome,
    )
    db.add(bet)
    db.commit()
    db.refresh(bet)
    return bet


def make_cup(
    db: Session,
    *,
    week_start: datetime | None = None,
    week_end: datetime | None = None,
    status: str = CupStatus.OPEN.value,
) -> Cup:
    start = week_start or datetime(2026, 1, 12, 0, 0, tzinfo=timezone.utc)
    cup = Cup(
        week_start=start,
        week_end=week_end or (start + timedelta(days=7)),
        status=status,
    )
    db.add(cup)
    db.commit()
    db.refresh(cup)
    return cup


def make_cup_entry(
    db: Session,
    *,
    cup: Cup,
    user: User,
    balance: Decimal = Decimal("1000.00"),
    final_rank: int | None = None,
) -> CupEntry:
    entry = CupEntry(
        cup_id=cup.id,
        user_id=user.id,
        balance=balance,
        final_rank=final_rank,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry
