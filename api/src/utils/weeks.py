from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from ..settings import CUP_TIMEZONE


def london_today(now: datetime) -> date:
    """The civil date in CUP_TIMEZONE at instant `now` (aware UTC)."""
    return now.astimezone(ZoneInfo(CUP_TIMEZONE)).date()


def current_week_window(now: datetime) -> tuple[datetime, datetime]:
    """The civil-week window (Monday 00:00 -> next Monday 00:00) in CUP_TIMEZONE
    that contains `now`, returned as aware UTC instants.

    Computed in civil terms so DST weeks (167/169h) resolve to the correct UTC
    span rather than a blind 7-day timedelta on a UTC instant. `now` must be
    aware UTC.
    """
    zone = ZoneInfo(CUP_TIMEZONE)
    local_now = now.astimezone(zone)

    monday_date = local_now.date() - timedelta(days=local_now.weekday())
    next_monday_date = monday_date + timedelta(days=7)

    start_local = datetime.combine(monday_date, time(0, 0), tzinfo=zone)
    end_local = datetime.combine(next_monday_date, time(0, 0), tzinfo=zone)

    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)
