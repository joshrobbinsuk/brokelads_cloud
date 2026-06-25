"""Ingestion writes/filters (internal_queries) and the job runner's due-gate and
dispatch. Network-backed jobs are exercised only through the DB-only settle jobs.
"""

from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from src.database import BaseModel
from src.models import (
    Bet,
    BetOutcome,
    Fixture,
    FixtureResult,
    JobControl,
    League,
)
from src.rapid_api.internal_queries import (
    fetch_bets_to_settle,
    fetch_fixtures_missing_odds,
    fetch_non_started_fixtures,
    fetch_voided_bets_to_settle,
    get_active_league_rapid_id,
    save_new_fixtures,
    update_fixtures,
)
from src.rapid_api.jobs import run_settle_voided_bets
from src.rapid_api.runner import run_jobs
from src.rapid_api.schemas.fixture import Fixture as FixtureSchema
from src.rapid_api.schemas.odds import Odds as OddsSchema
from src.tests.factories import make_bet, make_fixture, make_user


def _fixture_schema(rapid_id: int, status: str = "NS") -> FixtureSchema:
    return FixtureSchema.model_validate(
        {
            "fixture": {
                "id": rapid_id,
                "timestamp": 1893456000,
                "venue": {"name": "Stadium"},
                "status": {"short": status},
            },
            "teams": {
                "home": {"name": "Home FC", "logo": "h.png"},
                "away": {"name": "Away FC", "logo": "a.png"},
            },
        }
    )


def _odds_schema(bl_id: str, rapid_id: int, complete: bool = True) -> OddsSchema:
    values = [
        {"value": "Home", "odd": "2.00"},
        {"value": "Draw", "odd": "3.00"},
        {"value": "Away", "odd": "4.00"},
    ]
    if not complete:
        values = values[:1]
    odds = OddsSchema.model_validate(
        {
            "fixture": {"id": rapid_id},
            "bookmakers": [
                {
                    "id": 1,
                    "name": "Bet365",
                    "bets": [{"id": 1, "name": "Match Winner", "values": values}],
                }
            ],
        }
    )
    odds.bl_id = bl_id
    return odds


class TestSaveNewFixtures:
    def test_inserts_new_and_skips_existing_rapid_ids(self, db: Session) -> None:
        save_new_fixtures(db, [_fixture_schema(1), _fixture_schema(2)])
        assert db.query(Fixture).count() == 2

        # rapid_id 1 already stored; only 3 is new.
        save_new_fixtures(db, [_fixture_schema(1), _fixture_schema(3)])
        assert db.query(Fixture).count() == 3

    def test_empty_input_is_a_noop(self, db: Session) -> None:
        save_new_fixtures(db, [])
        assert db.query(Fixture).count() == 0


class TestUpdateFixtures:
    def test_writes_odds_onto_existing_fixture(self, db: Session) -> None:
        fixture = make_fixture(db, home_odds=None, away_odds=None, draw_odds=None)

        update_fixtures(
            db, [_odds_schema(bl_id=fixture.id, rapid_id=fixture.rapid_api_id)]
        )

        db.refresh(fixture)
        assert fixture.home_odds == Decimal("2.00")
        assert fixture.away_odds == Decimal("4.00")

    def test_incomplete_odds_row_is_filtered_out(self, db: Session) -> None:
        fixture = make_fixture(db, home_odds=None, away_odds=None, draw_odds=None)

        # to_db_dict() returns None for incomplete odds -> nothing to write, no error.
        update_fixtures(
            db,
            [
                _odds_schema(
                    bl_id=fixture.id, rapid_id=fixture.rapid_api_id, complete=False
                )
            ],
        )

        db.refresh(fixture)
        assert fixture.home_odds is None


class TestFetchFilters:
    def test_get_active_league_returns_rapid_id(self, db: Session) -> None:
        db.add(
            League(
                rapid_api_id=39, name="EPL", display_name="Premier League", active=True
            )
        )
        db.add(
            League(
                rapid_api_id=140, name="LaLiga", display_name="La Liga", active=False
            )
        )
        db.commit()
        assert get_active_league_rapid_id(db) == 39

    def test_get_active_league_none_when_no_active(self, db: Session) -> None:
        db.add(League(rapid_api_id=39, name="EPL", display_name="EPL", active=False))
        db.commit()
        assert get_active_league_rapid_id(db) is None

    def test_non_started_fixtures_excludes_finished(self, db: Session) -> None:
        make_fixture(db, status="NS")
        make_fixture(db, status="FT", home_goals=1, away_goals=0)
        result = fetch_non_started_fixtures(db)
        assert [f.status for f in result] == ["NS"]

    def test_fetch_reraises_on_db_error_rather_than_swallowing(
        self, db: Session
    ) -> None:
        # Read-path queries must surface a DB fault, not hide it as an empty result.
        BaseModel.metadata.drop_all(bind=db.get_bind())
        with pytest.raises(Exception):
            fetch_non_started_fixtures(db)

    def test_missing_odds_requires_all_three_null(self, db: Session) -> None:
        make_fixture(db, home_odds=None, away_odds=None, draw_odds=None)
        make_fixture(db, home_odds=Decimal("2.00"), away_odds=None, draw_odds=None)
        result = fetch_fixtures_missing_odds(db)
        assert len(result) == 1

    def test_bets_to_settle_only_undecided_on_finished_fixtures(
        self, db: Session
    ) -> None:
        user = make_user(db)
        played = make_fixture(db, status="FT", home_goals=2, away_goals=1)
        upcoming = make_fixture(db, status="NS")
        target = make_bet(
            db, user=user, fixture=played, outcome=BetOutcome.UNDECIDED.value
        )
        # Excluded: fixture not finished, and an already-settled bet on a finished fixture.
        make_bet(db, user=user, fixture=upcoming, outcome=BetOutcome.UNDECIDED.value)
        make_bet(db, user=user, fixture=played, outcome=BetOutcome.WON.value)

        result = fetch_bets_to_settle(db)
        assert [b.id for b in result] == [target.id]

    def test_voided_bets_to_settle_only_undecided_on_voided_fixtures(
        self, db: Session
    ) -> None:
        user = make_user(db)
        voided = make_fixture(db, status="PST")
        target = make_bet(
            db, user=user, fixture=voided, outcome=BetOutcome.UNDECIDED.value
        )
        make_bet(db, user=user, fixture=voided, outcome=BetOutcome.VOIDED.value)

        result = fetch_voided_bets_to_settle(db)
        assert [b.id for b in result] == [target.id]


class TestRunJobsDueGate:
    def _seed(self, db: Session, **kwargs: object) -> None:
        db.add(JobControl(job_name="settle_bets", **kwargs))
        db.commit()

    def _settleable_bet(self, db: Session) -> Bet:
        user = make_user(db, balance=Decimal("90.00"))
        fixture = make_fixture(db, status="FT", home_goals=2, away_goals=1)
        return make_bet(
            db,
            user=user,
            fixture=fixture,
            choice=FixtureResult.HOME,
            returns=Decimal("35.00"),
        )

    def test_due_job_runs_and_stamps_last_run_at(self, db: Session) -> None:
        self._seed(db, enabled=True, min_interval_seconds=300, last_run_at=None)
        bet = self._settleable_bet(db)

        run_jobs(db)

        db.refresh(bet)
        assert bet.outcome == BetOutcome.WON.value
        job = db.query(JobControl).filter_by(job_name="settle_bets").one()
        assert job.last_run_at is not None

    def test_disabled_job_does_not_run(self, db: Session) -> None:
        self._seed(db, enabled=False, min_interval_seconds=300, last_run_at=None)
        bet = self._settleable_bet(db)

        run_jobs(db)

        db.refresh(bet)
        assert bet.outcome == BetOutcome.UNDECIDED.value

    # NB: the "recently run -> skipped" path can't be exercised here. is_due()
    # compares against last_run_at, and SQLite strips the timezone on round-trip,
    # so an aware/naive comparison raises. Prod is Postgres (tz preserved). The
    # interval math itself is covered in-memory by test_models.TestJobControlIsDue.


class TestSettlementJobsThroughRegistry:
    def test_run_settle_voided_bets_refunds_stake(self, db: Session) -> None:
        user = make_user(db, balance=Decimal("90.00"))
        fixture = make_fixture(db, status="PST")
        bet = make_bet(db, user=user, fixture=fixture, stake=Decimal("10.00"))

        run_settle_voided_bets(db)

        db.refresh(bet)
        db.refresh(user)
        assert bet.outcome == BetOutcome.VOIDED.value
        assert user.balance == Decimal("100.00")

    def test_draw_bet_on_drawn_fixture_wins(self, db: Session) -> None:
        from src.rapid_api.jobs import run_settle_bets

        user = make_user(db, balance=Decimal("90.00"))
        fixture = make_fixture(db, status="FT", home_goals=1, away_goals=1)
        bet = make_bet(
            db,
            user=user,
            fixture=fixture,
            choice=FixtureResult.DRAW,
            returns=Decimal("40.00"),
        )

        run_settle_bets(db)

        db.refresh(bet)
        db.refresh(user)
        assert bet.outcome == BetOutcome.WON.value
        assert user.balance == Decimal("130.00")  # 90 + 40
