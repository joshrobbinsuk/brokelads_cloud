"""Weekly engagement streaks, computed on read from settled cups + entries.

A "week" is the London civil cup week (cups freeze their UTC bounds at creation).
A streak runs over consecutive calendar weeks in which the user has a SETTLED cup
entry, anchored at the most recent settled cup week overall — so a settled week
the user missed (or a week with no cup at all) between now and their last entry
breaks the streak. The current OPEN week is ignored (it can only extend a streak
once it settles).

No storage, no caching, no events dependency: this reads the domain tables. A
new streak kind is another `_walk` with its own predicate.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Callable

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from ..models import Cup, CupEntry, CupStatus, LedgerEntry, LedgerEntryType
from ..utils.logging import logger
from ..utils.weeks import current_week_window


@dataclass(frozen=True)
class _WeekEntry:
    """The user's settled entry for one week: its final balance and the grant it
    started from (the ENTRY_GRANT ledger amount — not a hardcoded stake, so a
    future variable grant stays correct)."""

    balance: Decimal
    grant: Decimal


def _week_key(dt: datetime) -> str:
    """Canonical key for a cup's civil-week start. Normalizes to a UTC wall-clock
    string so aware values (Postgres) and naive ones (SQLite) compare equal."""
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc)
    return dt.replace(tzinfo=None, microsecond=0).isoformat()


def _previous_week_start(week_start: datetime) -> datetime:
    """The civil-week start immediately before `week_start`, DST-correct."""
    ref = (
        week_start
        if week_start.tzinfo is not None
        else week_start.replace(tzinfo=timezone.utc)
    )
    return current_week_window(ref - timedelta(days=1))[0]


def _walk(
    anchor: datetime,
    weeks: dict[str, _WeekEntry],
    predicate: Callable[[_WeekEntry], bool],
) -> int:
    """Count consecutive weeks back from `anchor` while the user has a settled
    entry there and the predicate holds. A missing or failing week stops it."""
    count = 0
    cursor = anchor
    while True:
        entry = weeks.get(_week_key(cursor))
        if entry is None or not predicate(entry):
            break
        count += 1
        cursor = _previous_week_start(cursor)
    return count


def compute_streaks_bulk(db: Session, user_ids: list[str]) -> dict[str, dict[str, int]]:
    """Streak counts per user (one query set for the whole batch — no N+1)."""
    try:
        if not user_ids:
            return {}

        anchor = db.execute(
            select(func.max(Cup.week_start)).where(
                Cup.status == CupStatus.SETTLED.value
            )
        ).scalar()
        if anchor is None:
            return {
                user_id: {"participation_streak": 0, "profit_streak": 0}
                for user_id in user_ids
            }

        rows = db.execute(
            select(
                CupEntry.user_id,
                Cup.week_start,
                CupEntry.balance,
                LedgerEntry.amount,
            )
            .join(Cup, Cup.id == CupEntry.cup_id)
            .join(
                LedgerEntry,
                and_(
                    LedgerEntry.cup_entry_id == CupEntry.id,
                    LedgerEntry.type == LedgerEntryType.ENTRY_GRANT.value,
                ),
            )
            .where(
                Cup.status == CupStatus.SETTLED.value,
                CupEntry.user_id.in_(user_ids),
            )
        ).all()

        by_user: dict[str, dict[str, _WeekEntry]] = {
            user_id: {} for user_id in user_ids
        }
        for user_id, week_start, balance, grant in rows:
            by_user[user_id][_week_key(week_start)] = _WeekEntry(balance, grant)

        return {
            user_id: {
                "participation_streak": _walk(anchor, by_user[user_id], lambda _: True),
                "profit_streak": _walk(
                    anchor, by_user[user_id], lambda e: e.balance > e.grant
                ),
            }
            for user_id in user_ids
        }
    except Exception:
        logger.exception("Error computing streaks")
        raise


def compute_streaks(db: Session, user_id: str) -> dict[str, int]:
    """Streak counts for a single user."""
    try:
        return compute_streaks_bulk(db, [user_id])[user_id]
    except Exception:
        logger.exception(f"Error computing streaks for user {user_id}")
        raise
