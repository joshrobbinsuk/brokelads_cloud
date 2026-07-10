"""Pure model logic — properties and validators, no database."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from src.models import Bet, Fixture, JobControl, LedgerEntry, User


class TestFixtureHasOdds:
    def test_true_when_all_three_set(self) -> None:
        fixture = Fixture(
            home_odds=Decimal("2.00"),
            away_odds=Decimal("3.00"),
            draw_odds=Decimal("3.50"),
        )
        assert fixture.has_odds is True

    def test_false_when_any_missing(self) -> None:
        fixture = Fixture(
            home_odds=Decimal("2.00"), away_odds=Decimal("3.00"), draw_odds=None
        )
        assert fixture.has_odds is False


class TestFixtureOutcome:
    def test_home_win(self) -> None:
        assert Fixture(status="FT", home_goals=2, away_goals=1).outcome == "HOME"

    def test_away_win(self) -> None:
        assert Fixture(status="FT", home_goals=0, away_goals=1).outcome == "AWAY"

    def test_draw(self) -> None:
        assert Fixture(status="FT", home_goals=1, away_goals=1).outcome == "DRAW"

    def test_none_when_not_a_result_status(self) -> None:
        # Goals present but the match was postponed, not played to a result.
        assert Fixture(status="PST", home_goals=2, away_goals=1).outcome is None

    def test_none_when_goals_missing(self) -> None:
        assert Fixture(status="FT", home_goals=None, away_goals=None).outcome is None


class TestJobControlIsDue:
    def test_disabled_is_never_due(self) -> None:
        job = JobControl(enabled=False, min_interval_seconds=300, last_run_at=None)
        assert job.is_due() is False

    def test_due_when_never_run(self) -> None:
        job = JobControl(enabled=True, min_interval_seconds=300, last_run_at=None)
        assert job.is_due() is True

    def test_not_due_within_interval(self) -> None:
        recent = datetime.now(timezone.utc) - timedelta(seconds=60)
        job = JobControl(enabled=True, min_interval_seconds=300, last_run_at=recent)
        assert job.is_due() is False

    def test_due_after_interval(self) -> None:
        old = datetime.now(timezone.utc) - timedelta(seconds=600)
        job = JobControl(enabled=True, min_interval_seconds=300, last_run_at=old)
        assert job.is_due() is True


class TestValidators:
    def test_bad_user_status_rejected(self) -> None:
        with pytest.raises(ValueError):
            User(status="NONSENSE")

    def test_bad_bet_choice_rejected(self) -> None:
        with pytest.raises(ValueError):
            Bet(choice="MAYBE")

    def test_bad_bet_outcome_rejected(self) -> None:
        with pytest.raises(ValueError):
            Bet(outcome="PENDING")

    def test_bad_ledger_entry_type_rejected(self) -> None:
        with pytest.raises(ValueError):
            LedgerEntry(type="REFUND")
