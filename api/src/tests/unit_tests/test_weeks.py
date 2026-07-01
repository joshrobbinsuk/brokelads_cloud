"""Week-window logic — DB-independent, so asserted purely on the Python side."""

from datetime import datetime, timezone

from src.utils.weeks import current_week_window


def test_normal_week_is_seven_days_and_starts_monday_utc() -> None:
    # Wed 2026-01-14 12:00 UTC. London == UTC in January (GMT), so the local
    # Monday 00:00 is also 00:00 UTC.
    now = datetime(2026, 1, 14, 12, 0, tzinfo=timezone.utc)
    start, end = current_week_window(now)

    assert start == datetime(2026, 1, 12, 0, 0, tzinfo=timezone.utc)  # Monday
    assert end == datetime(2026, 1, 19, 0, 0, tzinfo=timezone.utc)
    assert (end - start).total_seconds() == 7 * 24 * 3600
    assert start <= now < end


def test_summer_bst_week_boundary_is_2300_utc() -> None:
    # July: London is BST (UTC+1), so local Monday 00:00 == 23:00 UTC Sunday.
    now = datetime(2026, 7, 15, 12, 0, tzinfo=timezone.utc)
    start, end = current_week_window(now)

    assert start == datetime(2026, 7, 12, 23, 0, tzinfo=timezone.utc)
    assert end == datetime(2026, 7, 19, 23, 0, tzinfo=timezone.utc)
    assert (end - start).total_seconds() == 7 * 24 * 3600


def test_winter_and_summer_windows_have_different_utc_offsets() -> None:
    winter_start, _ = current_week_window(
        datetime(2026, 1, 14, 12, 0, tzinfo=timezone.utc)
    )
    summer_start, _ = current_week_window(
        datetime(2026, 7, 15, 12, 0, tzinfo=timezone.utc)
    )
    # Same wall-clock boundary (Monday 00:00 London), different UTC instants.
    assert winter_start.hour == 0
    assert summer_start.hour == 23


def test_dst_spring_forward_week_is_167_hours() -> None:
    # UK clocks go forward at 01:00 on Sun 2026-03-29; that week is 23h short a
    # day => 167h. now sits inside the week beginning Mon 2026-03-23.
    now = datetime(2026, 3, 25, 12, 0, tzinfo=timezone.utc)
    start, end = current_week_window(now)

    assert start == datetime(2026, 3, 23, 0, 0, tzinfo=timezone.utc)  # GMT boundary
    assert end == datetime(2026, 3, 29, 23, 0, tzinfo=timezone.utc)  # BST boundary
    assert (end - start).total_seconds() == 167 * 3600
