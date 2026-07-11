"""Weekly streak computation, through client.streaks.compute_streaks.

Weeks are canonical London civil-week windows (current week + N back), built via
the same current_week_window the app uses so the walk's week arithmetic matches.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from src.client.streaks import compute_streaks
from src.models import CupStatus, LedgerEntry, LedgerEntryType, User
from src.settings import CUP_STARTING_STAKE
from src.tests.factories import make_cup, make_cup_entry, make_user
from src.utils.weeks import current_week_window

WeekWindow = tuple[datetime, datetime]


def _weeks(n: int) -> list[WeekWindow]:
    """Canonical week windows: index 0 is the current (open) week, 1 is last
    week, and so on, back n weeks."""
    windows = [current_week_window(datetime.now(timezone.utc))]
    for _ in range(n):
        windows.append(current_week_window(windows[-1][0] - timedelta(days=1)))
    return windows


def _bare_settled_cup(db: Session, week: WeekWindow) -> None:
    """A settled cup with no entries — establishes the global anchor week."""
    make_cup(db, week_start=week[0], week_end=week[1], status=CupStatus.SETTLED.value)


def _settled_entry(
    db: Session,
    week: WeekWindow,
    user: User,
    *,
    balance: Decimal,
    grant: Decimal = CUP_STARTING_STAKE,
    status: str = CupStatus.SETTLED.value,
) -> None:
    cup = make_cup(db, week_start=week[0], week_end=week[1], status=status)
    entry = make_cup_entry(db, cup=cup, user=user, balance=balance, final_rank=1)
    db.add(
        LedgerEntry(
            cup_entry_id=entry.id,
            type=LedgerEntryType.ENTRY_GRANT.value,
            amount=grant,
            balance_after=grant,
            bet_id=None,
        )
    )
    db.commit()


def test_fresh_user_has_zero_streaks(db: Session) -> None:
    user = make_user(db)
    assert compute_streaks(db, user.id) == {
        "participation_streak": 0,
        "profit_streak": 0,
    }


def test_settled_weeks_but_user_never_entered_is_zero(db: Session) -> None:
    user = make_user(db)
    weeks = _weeks(2)
    _bare_settled_cup(db, weeks[1])
    _bare_settled_cup(db, weeks[2])
    assert compute_streaks(db, user.id) == {
        "participation_streak": 0,
        "profit_streak": 0,
    }


def test_unbroken_run_counts_all_consecutive_weeks(db: Session) -> None:
    user = make_user(db)
    weeks = _weeks(3)
    for w in (weeks[1], weeks[2], weeks[3]):
        _settled_entry(db, w, user, balance=Decimal("1200.00"))

    assert compute_streaks(db, user.id) == {
        "participation_streak": 3,
        "profit_streak": 3,
    }


def test_open_current_week_neither_counts_nor_breaks(db: Session) -> None:
    user = make_user(db)
    weeks = _weeks(2)
    # Current (open) week entry + two settled weeks behind it.
    _settled_entry(
        db, weeks[0], user, balance=Decimal("1200.00"), status=CupStatus.OPEN.value
    )
    _settled_entry(db, weeks[1], user, balance=Decimal("1200.00"))
    _settled_entry(db, weeks[2], user, balance=Decimal("1200.00"))

    assert compute_streaks(db, user.id) == {
        "participation_streak": 2,
        "profit_streak": 2,
    }


def test_gap_resets_the_streak(db: Session) -> None:
    user = make_user(db)
    weeks = _weeks(3)
    # Entered the latest and the oldest settled week, but missed the middle one
    # (the cup existed and settled — a true gap).
    _settled_entry(db, weeks[1], user, balance=Decimal("1200.00"))
    _bare_settled_cup(db, weeks[2])
    _settled_entry(db, weeks[3], user, balance=Decimal("1200.00"))

    assert compute_streaks(db, user.id)["participation_streak"] == 1


def test_missing_the_latest_settled_week_breaks_it(db: Session) -> None:
    user = make_user(db)
    weeks = _weeks(3)
    # A newer settled week exists that the user missed -> streak not current.
    _bare_settled_cup(db, weeks[1])
    _settled_entry(db, weeks[2], user, balance=Decimal("1200.00"))
    _settled_entry(db, weeks[3], user, balance=Decimal("1200.00"))

    assert compute_streaks(db, user.id)["participation_streak"] == 0


def test_non_adjacent_week_with_no_cup_breaks_it(db: Session) -> None:
    user = make_user(db)
    weeks = _weeks(3)
    # weeks[2] never had a cup at all -> the walk stops there.
    _settled_entry(db, weeks[1], user, balance=Decimal("1200.00"))
    _settled_entry(db, weeks[3], user, balance=Decimal("1200.00"))

    assert compute_streaks(db, user.id)["participation_streak"] == 1


def test_profit_stops_at_even_or_loss_but_participation_continues(
    db: Session,
) -> None:
    user = make_user(db)
    weeks = _weeks(3)
    _settled_entry(db, weeks[1], user, balance=Decimal("1200.00"))  # profit
    _settled_entry(db, weeks[2], user, balance=Decimal("1000.00"))  # even == grant
    _settled_entry(db, weeks[3], user, balance=Decimal("800.00"))  # loss

    result = compute_streaks(db, user.id)
    assert result["participation_streak"] == 3
    assert result["profit_streak"] == 1


def test_profit_compares_against_the_entrys_own_grant_not_a_constant(
    db: Session,
) -> None:
    user = make_user(db)
    weeks = _weeks(2)
    # Grant of 500, not the usual 1000: profit is balance > 500, not > 1000.
    _settled_entry(
        db, weeks[1], user, balance=Decimal("600.00"), grant=Decimal("500.00")
    )
    _settled_entry(
        db, weeks[2], user, balance=Decimal("500.00"), grant=Decimal("500.00")
    )  # even against its own grant

    result = compute_streaks(db, user.id)
    assert result["participation_streak"] == 2
    assert result["profit_streak"] == 1
