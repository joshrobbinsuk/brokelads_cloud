"""Which cup is this week's, and making sure it exists.

The one fact both feature packages need: `rapid_api` opens the week's cup on the
Monday rollover tick, `client` reads it on every request and falls back to
opening it if that tick never landed. Settling a cup is a job step
(`rapid_api/internal_queries.py`); rendering one is an API concern
(`client/cup.py`); only its existence is shared.
"""

from datetime import datetime

from sqlalchemy.orm import Session

from .models import Cup, CupStatus
from .utils.logging import logger
from .utils.weeks import current_week_window


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
