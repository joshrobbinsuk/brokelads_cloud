from datetime import datetime, timezone
from decimal import Decimal
from typing import Sequence

from sqlalchemy.engine import RowMapping
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, select, or_

from ..models import (
    Bet,
    CupEntry,
    Fixture,
    League,
    User,
    FixtureResult,
    TransactionRecord,
    TransactionType,
    UserStatus,
)
from ..utils.logging import logger
from ..settings import (
    NOT_STARTED_STATUSES,
    PUNDIT_RECENT_BET_LIMIT,
)
from ..utils.weeks import current_week_window
from .cup import get_or_create_current_cup, get_or_create_entry


class ClientSideError(Exception):
    pass


class UsernameTakenError(Exception):
    pass


def get_user(db: Session, user_id: str) -> User | None:
    try:
        return db.query(User).filter(User.id == user_id).first()
    except Exception:
        logger.exception(f"Error fetching user {user_id}")
        raise


def get_user_by_cognito_id(db: Session, cognito_uuid: str) -> User | None:
    try:
        return db.query(User).filter(User.cognito_uuid == cognito_uuid).first()
    except Exception:
        logger.exception(f"Error fetching user by cognito_uuid {cognito_uuid}")
        raise


def get_or_create_user(db: Session, cognito_uuid: str, email: str) -> User:
    try:
        user = get_user_by_cognito_id(db, cognito_uuid)

        if not user:
            user = User(
                cognito_uuid=cognito_uuid,
                email=email,
                status=UserStatus.ACTIVE.value,
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            logger.info(f"Created new user: {email} ({cognito_uuid})")

        return user
    except Exception:
        db.rollback()
        logger.exception(f"Error getting or creating user {email}")
        raise


def set_username(db: Session, user: User, username: str) -> User:
    """Set a user's display name once. Format is validated at the request schema;
    here we enforce set-once and case-insensitive uniqueness. The DB unique
    constraint is an exact-case backstop; a case-insensitive race is accepted at
    friends scale (see CLAUDE.md Known gaps)."""
    try:
        if user.username is not None:
            raise ClientSideError("Username is already set")

        existing = (
            db.query(User).filter(func.lower(User.username) == username.lower()).first()
        )
        if existing is not None:
            raise UsernameTakenError(username)

        user.username = username
        db.commit()
        db.refresh(user)
        logger.info(f"User {user.email} set username {username}")
        return user
    except (ClientSideError, UsernameTakenError):
        # Normal domain rejections (taken / already set) — re-raise without the
        # logger.exception below (they aren't faults) and without a rollback
        # (they're detected before any write).
        raise
    except Exception:
        db.rollback()
        logger.exception(f"Error setting username for {user.email}")
        raise


def get_active_leagues(db: Session) -> list[League]:
    try:
        return db.query(League).filter(League.active.is_(True)).all()
    except Exception:
        logger.exception("Error fetching active leagues")
        raise


def fetch_non_started_fixtures_with_odds(
    db: Session,
    search: str | None = None,
    league_id: str | None = None,
) -> list[Fixture]:

    try:
        week_start, week_end = current_week_window(datetime.now(timezone.utc))
        query = (
            db.query(Fixture)
            .options(joinedload(Fixture.league))
            .filter(
                Fixture.status.in_(NOT_STARTED_STATUSES),
                Fixture.league_id.isnot(None),
                Fixture.home_odds.isnot(None),
                Fixture.away_odds.isnot(None),
                Fixture.draw_odds.isnot(None),
                Fixture.kick_off >= week_start,
                Fixture.kick_off < week_end,
            )
        )

        if league_id:
            query = query.filter(Fixture.league_id == league_id)

        if search:
            pattern = f"%{search}%"
            query = query.filter(
                or_(
                    Fixture.home_team.ilike(pattern),
                    Fixture.away_team.ilike(pattern),
                    Fixture.venue.ilike(pattern),
                )
            )

        # No cap: show the whole current week's fixtures (the week-window filter
        # above bounds the set; a busy week is a long scroll, by design).
        return query.order_by(Fixture.kick_off.asc()).all()
    except Exception:
        logger.exception("Error fetching non-started fixtures with odds")
        raise


def fetch_visible_fixture_slate_by_ids(
    db: Session, fixture_ids: Sequence[str]
) -> list[Fixture]:
    """Of the requested ids, return only those in the current visible slate
    (not-started, all three odds present, in the current week), in request order
    with duplicates removed."""
    try:
        visible = fetch_non_started_fixtures_with_odds(db)
        by_id = {fixture.id: fixture for fixture in visible}

        ordered: list[Fixture] = []
        seen: set[str] = set()
        for fixture_id in fixture_ids:
            if fixture_id in seen:
                continue
            seen.add(fixture_id)
            fixture = by_id.get(fixture_id)
            if fixture is not None:
                ordered.append(fixture)
        return ordered
    except Exception:
        logger.exception("Error fetching visible fixture slate by ids")
        raise


def get_recent_user_bets_for_pundit(
    db: Session,
    user_id: str,
    limit: int = PUNDIT_RECENT_BET_LIMIT,
) -> Sequence[RowMapping]:
    try:
        return get_user_bets(db, user_id, limit=limit)
    except Exception:
        logger.exception(f"Error fetching recent bets for pundit, user {user_id}")
        raise


def get_user_bets(
    db: Session,
    user_id: str,
    outcome: str | None = None,
    search: str | None = None,
    limit: int | None = 30,
    cup_id: str | None = None,
) -> Sequence[RowMapping]:
    try:
        stmt = (
            select(
                Bet.id.label("id"),
                Bet.user_id.label("user_id"),
                Bet.fixture_id.label("fixture_id"),
                Bet.cup_entry_id.label("cup_entry_id"),
                Fixture.home_team.label("home_team"),
                Fixture.away_team.label("away_team"),
                Fixture.kick_off.label("kick_off"),
                Bet.choice.label("choice"),
                Bet.stake.label("stake"),
                Bet.returns.label("returns"),
                Bet.outcome.label("outcome"),
                Bet.created_at.label("created_at"),
            )
            .join(Fixture, Fixture.id == Bet.fixture_id)
            .where(Bet.user_id == user_id)
        )

        if cup_id:
            stmt = stmt.join(CupEntry, CupEntry.id == Bet.cup_entry_id).where(
                CupEntry.cup_id == cup_id
            )

        if outcome:
            stmt = stmt.where(Bet.outcome == outcome)

        if search:
            pattern = f"%{search}%"
            stmt = stmt.where(
                or_(
                    Fixture.home_team.ilike(pattern),
                    Fixture.away_team.ilike(pattern),
                    Fixture.venue.ilike(pattern),
                )
            )

        stmt = stmt.order_by(Bet.created_at.desc())

        if limit:
            stmt = stmt.limit(limit)

        rows = db.execute(stmt).mappings().all()
        return rows

    except Exception:
        logger.exception(f"Error fetching bets for user {user_id}")
        raise


def create_bet(
    db: Session,
    user: User,
    fixture_id: str,
    choice: FixtureResult,
    stake: Decimal,
) -> dict[str, object]:
    try:
        now = datetime.now(timezone.utc)
        fixture = db.query(Fixture).filter(Fixture.id == fixture_id).first()
        if not fixture or not fixture.has_odds:
            raise ClientSideError("Invalid fixture or fixture does not have odds")

        if fixture.status not in NOT_STARTED_STATUSES:
            raise ClientSideError("Fixture has already started")

        cup = get_or_create_current_cup(db, now)
        if not (cup.week_start <= fixture.kick_off < cup.week_end):
            raise ClientSideError("Fixture is outside this week's cup")

        entry = get_or_create_entry(db, cup, user)
        # Not row-locked: accepted for friends-scale v1 (see CLAUDE.md Known gaps).
        if entry.balance < stake:
            raise ClientSideError("Insufficient funds")

        odds_map = {
            FixtureResult.HOME: fixture.home_odds,
            FixtureResult.AWAY: fixture.away_odds,
            FixtureResult.DRAW: fixture.draw_odds,
        }

        odds = odds_map.get(choice)
        if odds is None:
            raise ClientSideError("Fixture odds are unavailable")
        returns = (stake * odds) + stake

        bet = Bet(
            user_id=user.id,
            fixture_id=fixture.id,
            cup_entry_id=entry.id,
            choice=choice.value,
            stake=stake,
            returns=returns,
        )

        balance_before = entry.balance
        entry.debit(stake)

        transaction = TransactionRecord(
            bet=bet,
            type=TransactionType.BET.value,
            user_balance_before=balance_before,
            user_balance_after=entry.balance,
        )

        db.add(bet)
        db.add(transaction)
        db.commit()

        return {"id": bet.id, "returns": bet.returns}

    except ClientSideError:
        # Expected domain rejection (bad fixture, insufficient funds, …) — control
        # flow, not a fault. No writes have happened yet, so nothing to roll back.
        raise
    except Exception:
        db.rollback()
        logger.exception("Error creating bet")
        raise
