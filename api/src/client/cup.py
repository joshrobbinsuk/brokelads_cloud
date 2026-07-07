from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Cup, CupEntry, CupStatus, User
from ..settings import CUP_STARTING_STAKE
from ..utils.logging import logger
from ..utils.weeks import current_week_window


def get_or_create_current_cup(db: Session, now: datetime) -> Cup:
    """Upsert this week's cup (write path). Stores the resolved UTC bounds once."""
    try:
        week_start, week_end = current_week_window(now)
        cup = db.query(Cup).filter(Cup.week_start == week_start).first()
        if cup is None:
            cup = Cup(
                week_start=week_start,
                week_end=week_end,
                status=CupStatus.OPEN.value,
            )
            db.add(cup)
            db.commit()
            db.refresh(cup)
            logger.info(f"Created cup for week starting {week_start.isoformat()}")
        return cup
    except Exception:
        db.rollback()
        logger.exception("Error getting or creating current cup")
        raise


def get_current_cup(db: Session, now: datetime) -> Cup | None:
    """Lookup only (read path) — never writes."""
    try:
        week_start, _ = current_week_window(now)
        return db.query(Cup).filter(Cup.week_start == week_start).first()
    except Exception:
        logger.exception("Error fetching current cup")
        raise


def get_cup_by_id(db: Session, cup_id: str) -> Cup | None:
    try:
        return db.query(Cup).filter(Cup.id == cup_id).first()
    except Exception:
        logger.exception(f"Error fetching cup {cup_id}")
        raise


def get_or_create_entry(db: Session, cup: Cup, user: User) -> CupEntry:
    try:
        entry = (
            db.query(CupEntry)
            .filter(CupEntry.cup_id == cup.id, CupEntry.user_id == user.id)
            .first()
        )
        if entry is None:
            entry = CupEntry(
                cup_id=cup.id,
                user_id=user.id,
                balance=CUP_STARTING_STAKE,
            )
            db.add(entry)
            db.commit()
            db.refresh(entry)
        return entry
    except Exception:
        db.rollback()
        logger.exception("Error getting or creating cup entry")
        raise


def current_balance(db: Session, user: User, now: datetime) -> Decimal:
    """The user's balance in the current cup, or the starting stake if they have
    not entered yet. Never creates rows."""
    try:
        cup = get_current_cup(db, now)
        if cup is None:
            return CUP_STARTING_STAKE
        entry = (
            db.query(CupEntry)
            .filter(CupEntry.cup_id == cup.id, CupEntry.user_id == user.id)
            .first()
        )
        return entry.balance if entry is not None else CUP_STARTING_STAKE
    except Exception:
        logger.exception("Error reading current cup balance")
        raise


def leaderboard(db: Session, cup: Cup) -> list[dict[str, object]]:
    """Entries ordered by balance desc, with username, winner flag, and each
    user's lifetime cup wins (aggregated in-query to avoid an N+1)."""
    try:
        wins = (
            select(
                CupEntry.user_id.label("user_id"),
                func.count(CupEntry.id).label("cups_won"),
            )
            .where(CupEntry.is_winner.is_(True))
            .group_by(CupEntry.user_id)
            .subquery()
        )
        stmt = (
            select(
                CupEntry.user_id.label("user_id"),
                User.username.label("username"),
                User.avatar.label("avatar"),
                CupEntry.balance.label("balance"),
                CupEntry.is_winner.label("is_winner"),
                func.coalesce(wins.c.cups_won, 0).label("cups_won"),
            )
            .join(User, User.id == CupEntry.user_id)
            .outerjoin(wins, wins.c.user_id == CupEntry.user_id)
            .where(CupEntry.cup_id == cup.id)
            # user_id is the final tiebreaker so ordering is deterministic even
            # when a username is null (a user who bet before onboarding).
            .order_by(
                CupEntry.balance.desc(),
                User.username.asc(),
                CupEntry.user_id.asc(),
            )
        )
        rows = db.execute(stmt).mappings().all()
        return [
            {
                "rank": index + 1,
                "user_id": row["user_id"],
                "username": row["username"],
                "avatar": row["avatar"],
                "balance": str(row["balance"]),
                "is_winner": row["is_winner"],
                "cups_won": row["cups_won"],
            }
            for index, row in enumerate(rows)
        ]
    except Exception:
        logger.exception("Error building cup leaderboard")
        raise


def cups_won(db: Session, user: User) -> int:
    try:
        return (
            db.query(func.count(CupEntry.id))
            .filter(CupEntry.user_id == user.id, CupEntry.is_winner.is_(True))
            .scalar()
            or 0
        )
    except Exception:
        logger.exception("Error counting cups won")
        raise


def list_cups(db: Session) -> list[Cup]:
    """For the week selector, most-recent first."""
    try:
        return db.query(Cup).order_by(Cup.week_start.desc()).all()
    except Exception:
        logger.exception("Error listing cups")
        raise
