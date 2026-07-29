from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Sequence

from sqlalchemy.engine import RowMapping
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, select, or_

from ..models import (
    Bet,
    CupEntry,
    EventType,
    Fixture,
    League,
    PunditUsage,
    User,
    FixtureResult,
    LedgerEntry,
    LedgerEntryType,
    UserStatus,
    record_event,
)
from ..utils.logging import logger
from ..settings import (
    NOT_STARTED_STATUSES,
    PUNDIT_RECENT_BET_LIMIT,
)
from ..utils.weeks import current_week_window
from .cup import get_or_create_current_cup, get_or_create_entry


class ClientErrorCode(str, Enum):
    """Machine-readable codes for domain rejections — the wire contract the
    frontend branches on. The prose message is for display only."""

    FIXTURE_INVALID_OR_NO_ODDS = "FIXTURE_INVALID_OR_NO_ODDS"
    FIXTURE_STARTED = "FIXTURE_STARTED"
    FIXTURE_OUTSIDE_CUP_WEEK = "FIXTURE_OUTSIDE_CUP_WEEK"
    INSUFFICIENT_FUNDS = "INSUFFICIENT_FUNDS"
    ODDS_UNAVAILABLE = "ODDS_UNAVAILABLE"


class ClientSideError(Exception):
    def __init__(self, code: ClientErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class UsernameTakenError(Exception):
    pass


def get_user(db: Session, user_id: str) -> User | None:
    try:
        return db.query(User).filter(User.id == user_id).first()
    except Exception:
        logger.exception(f"Error fetching user {user_id}")
        raise


def get_user_by_auth_uid(db: Session, auth_uid: str) -> User | None:
    try:
        return db.query(User).filter(User.auth_uid == auth_uid).first()
    except Exception:
        logger.exception(f"Error fetching user by auth_uid {auth_uid}")
        raise


def get_or_create_user(db: Session, auth_uid: str, email: str) -> User:
    try:
        user = get_user_by_auth_uid(db, auth_uid)

        if not user:
            user = User(
                auth_uid=auth_uid,
                email=email,
                status=UserStatus.ACTIVE.value,
            )
            db.add(user)
            db.flush()
            record_event(db, EventType.USER_CREATED, user.id, {"email": email})
            db.commit()
            db.refresh(user)
            logger.info(f"Created new user: {email} ({auth_uid})")

        return user
    except Exception:
        db.rollback()
        logger.exception(f"Error getting or creating user {email}")
        raise


def set_username(db: Session, user: User, username: str) -> User:
    """Set or change a user's display name. Format is validated at the request
    schema; here we enforce case-insensitive uniqueness (excluding the caller's
    own row, so changing only your casing succeeds). The functional unique
    index on lower(username) is the backstop — a concurrent race past this
    pre-check surfaces as an IntegrityError/500, not a silent duplicate."""
    try:
        existing = (
            db.query(User)
            .filter(func.lower(User.username) == username.lower(), User.id != user.id)
            .first()
        )
        if existing is not None:
            raise UsernameTakenError(username)

        user.username = username
        db.commit()
        db.refresh(user)
        logger.info(f"User {user.email} set username {username}")
        return user
    except UsernameTakenError:
        # Normal domain rejection (taken) — re-raise without the logger.exception
        # below (it isn't a fault) and without a rollback (detected before any
        # write).
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
                )
            )

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


def pundit_count_today(db: Session, user: User, today: date) -> int:
    try:
        row = (
            db.query(PunditUsage)
            .filter(PunditUsage.user_id == user.id, PunditUsage.day == today)
            .first()
        )
        return row.count if row is not None else 0
    except Exception:
        logger.exception(f"Error reading pundit usage for user {user.id}")
        raise


def increment_pundit_usage(db: Session, user: User, today: date) -> None:
    try:
        row = (
            db.query(PunditUsage)
            .filter(PunditUsage.user_id == user.id, PunditUsage.day == today)
            .first()
        )
        if row is None:
            row = PunditUsage(user_id=user.id, day=today, count=0)
            db.add(row)
        row.count += 1
        db.commit()
    except Exception:
        db.rollback()
        logger.exception(f"Error incrementing pundit usage for user {user.id}")
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
            raise ClientSideError(
                ClientErrorCode.FIXTURE_INVALID_OR_NO_ODDS,
                "Invalid fixture or fixture does not have odds",
            )

        if fixture.status not in NOT_STARTED_STATUSES:
            raise ClientSideError(
                ClientErrorCode.FIXTURE_STARTED, "Fixture has already started"
            )

        cup = get_or_create_current_cup(db, now)
        if not (cup.week_start <= fixture.kick_off < cup.week_end):
            raise ClientSideError(
                ClientErrorCode.FIXTURE_OUTSIDE_CUP_WEEK,
                "Fixture is outside this week's cup",
            )

        entry = get_or_create_entry(db, cup, user)
        # Not row-locked: accepted for friends-scale v1 (see CLAUDE.md Known gaps).
        if entry.balance < stake:
            raise ClientSideError(
                ClientErrorCode.INSUFFICIENT_FUNDS, "Insufficient funds"
            )

        odds_map = {
            FixtureResult.HOME: fixture.home_odds,
            FixtureResult.AWAY: fixture.away_odds,
            FixtureResult.DRAW: fixture.draw_odds,
        }

        odds = odds_map.get(choice)
        if odds is None:
            raise ClientSideError(
                ClientErrorCode.ODDS_UNAVAILABLE, "Fixture odds are unavailable"
            )
        # Decimal odds already include the stake in the total return.
        returns = stake * odds

        bet = Bet(
            user_id=user.id,
            fixture_id=fixture.id,
            cup_entry_id=entry.id,
            choice=choice.value,
            stake=stake,
            returns=returns,
            odds_struck=odds,
        )

        entry.debit(stake)

        ledger_entry = LedgerEntry(
            cup_entry_id=entry.id,
            bet=bet,
            type=LedgerEntryType.BET_STAKE.value,
            amount=-stake,
            balance_after=entry.balance,
        )

        db.add(bet)
        db.add(ledger_entry)
        db.flush()
        record_event(
            db,
            EventType.BET_PLACED,
            user.id,
            {
                "bet_id": bet.id,
                "fixture_id": fixture.id,
                "choice": choice.value,
                "stake": str(stake),
                "odds_struck": str(odds),
            },
        )
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
