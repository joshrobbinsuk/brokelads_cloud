from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import (
    Bet,
    BetOutcome,
    Cup,
    CupEntry,
    CupStatus,
    EventType,
    LedgerEntry,
    LedgerEntryType,
    User,
    record_event,
)
from ..settings import CUP_STARTING_STAKE
from ..utils.logging import logger
from ..utils.weeks import current_week_window
from .streaks import compute_streaks_bulk


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
            db.flush()
            db.add(
                LedgerEntry(
                    cup_entry_id=entry.id,
                    type=LedgerEntryType.ENTRY_GRANT.value,
                    amount=CUP_STARTING_STAKE,
                    balance_after=CUP_STARTING_STAKE,
                    bet_id=None,
                )
            )
            record_event(
                db,
                EventType.CUP_ENTRY_CREATED,
                user.id,
                {"cup_id": cup.id, "entry_id": entry.id},
            )
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
    """Leaderboard rows for a cup. A settled cup serves its frozen `final_rank`
    (deleted entries leave honest gaps); an open/closing cup ranks live by
    balance. Each row carries the user's lifetime cup wins and their `potential`
    — balance plus the returns of every still-open bet, i.e. the most they could
    end the week with (both aggregated in-query to avoid an N+1)."""
    try:
        settled = cup.status == CupStatus.SETTLED.value
        wins = (
            select(
                CupEntry.user_id.label("user_id"),
                func.count(CupEntry.id).label("cups_won"),
            )
            .where(CupEntry.final_rank == 1)
            .group_by(CupEntry.user_id)
            .subquery()
        )
        open_returns = (
            select(
                Bet.cup_entry_id.label("cup_entry_id"),
                func.sum(Bet.returns).label("open_returns"),
            )
            .where(Bet.outcome == BetOutcome.UNDECIDED.value)
            .group_by(Bet.cup_entry_id)
            .subquery()
        )
        stmt = (
            select(
                CupEntry.user_id.label("user_id"),
                User.username.label("username"),
                CupEntry.balance.label("balance"),
                CupEntry.final_rank.label("final_rank"),
                func.coalesce(wins.c.cups_won, 0).label("cups_won"),
                func.coalesce(open_returns.c.open_returns, 0).label("open_returns"),
            )
            .join(User, User.id == CupEntry.user_id)
            .outerjoin(wins, wins.c.user_id == CupEntry.user_id)
            .outerjoin(open_returns, open_returns.c.cup_entry_id == CupEntry.id)
            .where(CupEntry.cup_id == cup.id)
        )
        if settled:
            stmt = stmt.order_by(
                CupEntry.final_rank.asc(),
                User.username.asc(),
                CupEntry.user_id.asc(),
            )
        else:
            # user_id is the final tiebreaker so ordering is deterministic even
            # when a username is null (a user who bet before onboarding).
            stmt = stmt.order_by(
                CupEntry.balance.desc(),
                User.username.asc(),
                CupEntry.user_id.asc(),
            )
        rows = db.execute(stmt).mappings().all()
        streaks = compute_streaks_bulk(db, [row["user_id"] for row in rows])
        return [
            {
                "rank": row["final_rank"] if settled else index + 1,
                "user_id": row["user_id"],
                "username": row["username"],
                "balance": str(row["balance"]),
                "potential": str(row["balance"] + row["open_returns"]),
                "is_winner": row["final_rank"] == 1,
                "cups_won": row["cups_won"],
                "participation_streak": streaks[row["user_id"]]["participation_streak"],
                "profit_streak": streaks[row["user_id"]]["profit_streak"],
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
            .filter(CupEntry.user_id == user.id, CupEntry.final_rank == 1)
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


def best_weeks(db: Session, limit: int = 5) -> list[dict[str, object]]:
    """All-time biggest single-week pots across settled cups, biggest first.
    Raw entries rather than one per user, so a punter on a run holds several
    places. Competition-ranked like the cup itself (equal pots share a rank)
    and cut at rank `limit`, so a tie is never split. Open/closing cups are
    excluded: only frozen pots count."""
    try:
        stmt = (
            select(
                CupEntry.user_id.label("user_id"),
                User.username.label("username"),
                CupEntry.balance.label("balance"),
                Cup.id.label("cup_id"),
                Cup.week_start.label("week_start"),
            )
            .join(User, User.id == CupEntry.user_id)
            .join(Cup, Cup.id == CupEntry.cup_id)
            .where(Cup.status == CupStatus.SETTLED.value)
            .order_by(
                CupEntry.balance.desc(),
                Cup.week_start.desc(),
                CupEntry.user_id.asc(),
            )
            .limit(100)
        )
        rows = db.execute(stmt).mappings().all()
        ranked: list[dict[str, object]] = []
        rank = 0
        for index, row in enumerate(rows):
            if index == 0 or row["balance"] < rows[index - 1]["balance"]:
                rank = index + 1
            if rank > limit:
                break
            ranked.append(
                {
                    "rank": rank,
                    "user_id": row["user_id"],
                    "username": row["username"],
                    "balance": str(row["balance"]),
                    "cup_id": row["cup_id"],
                    "week_start": row["week_start"],
                }
            )
        return ranked
    except Exception:
        logger.exception("Error building best weeks")
        raise


def best_week(db: Session, user: User) -> dict[str, object] | None:
    """The user's biggest settled-week pot and when it was, or None before
    their first settled cup."""
    try:
        stmt = (
            select(
                CupEntry.balance.label("balance"),
                Cup.week_start.label("week_start"),
            )
            .join(Cup, Cup.id == CupEntry.cup_id)
            .where(
                CupEntry.user_id == user.id,
                Cup.status == CupStatus.SETTLED.value,
            )
            .order_by(CupEntry.balance.desc(), Cup.week_start.desc())
            .limit(1)
        )
        row = db.execute(stmt).mappings().first()
        if row is None:
            return None
        return {"balance": str(row["balance"]), "week_start": row["week_start"]}
    except Exception:
        logger.exception("Error finding best week")
        raise
