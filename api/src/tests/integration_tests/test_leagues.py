"""Leagues ingestion: upsert_leagues semantics and the per-league
run_fetch_fixtures loop (active-only, target gate, league_id stamping).
The external API call is monkeypatched, so no network/API key is needed.
"""

import pytest
from sqlalchemy.orm import Session

from src.models import Fixture, League
from src.rapid_api import jobs as jobs_module
from src.rapid_api.internal_queries import (
    count_non_started_fixtures_by_league,
    get_active_leagues,
    save_new_fixtures,
    upsert_leagues,
)
from src.rapid_api.jobs import run_fetch_fixtures
from src.rapid_api.schemas.fixture import Fixture as FixtureSchema
from src.rapid_api.schemas.league import League as LeagueSchema
from src.tests.factories import make_fixture, make_league


def _league_schema(rapid_id: int, name: str = "Premier League") -> LeagueSchema:
    return LeagueSchema.model_validate(
        {
            "league": {
                "id": rapid_id,
                "name": name,
                "type": "League",
                "logo": "logo.png",
            },
            "country": {"name": "England"},
        }
    )


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


class TestUpsertLeagues:
    def test_inserts_new_leagues_inactive(self, db: Session) -> None:
        upsert_leagues(db, [_league_schema(39), _league_schema(140, "La Liga")])

        leagues = db.query(League).all()
        assert len(leagues) == 2
        assert all(not league.active for league in leagues)
        epl = db.query(League).filter_by(rapid_api_id=39).one()
        assert epl.display_name == "Premier League"
        assert epl.logo == "logo.png"
        assert epl.country == "England"
        assert epl.type == "League"

    def test_preserves_active_and_display_name_on_existing(self, db: Session) -> None:
        make_league(
            db,
            rapid_api_id=39,
            name="Premier League",
            display_name="EPL",
            active=True,
        )

        upsert_leagues(db, [_league_schema(39, name="English Premier League")])

        league = db.query(League).filter_by(rapid_api_id=39).one()
        assert league.active is True  # never touched
        assert league.display_name == "EPL"  # admin-curated, never touched
        assert league.name == "English Premier League"  # metadata refreshed

    def test_empty_input_is_a_noop(self, db: Session) -> None:
        upsert_leagues(db, [])
        assert db.query(League).count() == 0


class TestSaveNewFixturesBackfill:
    def test_backfills_league_id_on_existing_leagueless_row_no_duplicate(
        self, db: Session
    ) -> None:
        league = make_league(db, rapid_api_id=39)
        # Pre-existing row (rapid_api_id=1 per factory) with no league yet.
        existing = make_fixture(db, status="NS", league_id=None)
        assert existing.rapid_api_id == 1

        save_new_fixtures(db, [_fixture_schema(1)], league_id=league.id)

        db.refresh(existing)
        assert existing.league_id == league.id
        # Healed in place — exactly one row for rapid_api_id 1, no duplicate.
        assert db.query(Fixture).filter_by(rapid_api_id=1).count() == 1

    def test_does_not_overwrite_an_already_set_league_id(self, db: Session) -> None:
        original = make_league(db, rapid_api_id=39)
        other = make_league(db, rapid_api_id=140, name="La Liga")
        existing = make_fixture(db, status="NS", league_id=original.id)

        save_new_fixtures(db, [_fixture_schema(1)], league_id=other.id)

        db.refresh(existing)
        assert existing.league_id == original.id

    def test_inserts_new_and_backfills_existing_in_one_call(self, db: Session) -> None:
        league = make_league(db, rapid_api_id=39)
        existing = make_fixture(db, status="NS", league_id=None)  # rapid_api_id=1

        save_new_fixtures(
            db, [_fixture_schema(1), _fixture_schema(2)], league_id=league.id
        )

        db.refresh(existing)
        assert existing.league_id == league.id
        assert db.query(Fixture).count() == 2
        new_row = db.query(Fixture).filter_by(rapid_api_id=2).one()
        assert new_row.league_id == league.id


class TestRunFetchFixturesPerLeague:
    def _patch_fetch(
        self, monkeypatch: pytest.MonkeyPatch, returns: list[FixtureSchema]
    ) -> list[int]:
        called_with: list[int] = []

        def fake_fetch(league_id: int, next: int = 20) -> list[FixtureSchema]:
            called_with.append(league_id)
            return returns

        monkeypatch.setattr(jobs_module, "fetch_fixtures_by_league", fake_fetch)
        return called_with

    def test_skips_inactive_leagues(
        self, db: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        make_league(db, rapid_api_id=39, active=False)
        called = self._patch_fetch(monkeypatch, [])

        run_fetch_fixtures(db)

        assert called == []

    def test_fetches_under_target_and_stamps_league_id(
        self, db: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        league = make_league(db, rapid_api_id=39, active=True)
        called = self._patch_fetch(
            monkeypatch, [_fixture_schema(101), _fixture_schema(102)]
        )

        run_fetch_fixtures(db)

        assert called == [39]
        saved = db.query(Fixture).all()
        assert len(saved) == 2
        assert all(f.league_id == league.id for f in saved)

    def test_skips_league_at_target(
        self, db: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        league = make_league(db, rapid_api_id=39, active=True)
        for i in range(jobs_module.N_FIXTURES_PER_LEAGUE):
            make_fixture(db, status="NS", league_id=league.id)
        called = self._patch_fetch(monkeypatch, [_fixture_schema(101)])

        run_fetch_fixtures(db)

        assert called == []


class TestCountNonStartedFixturesByLeague:
    def test_counts_only_not_started_for_the_league(self, db: Session) -> None:
        a = make_league(db, rapid_api_id=39)
        b = make_league(db, rapid_api_id=140, name="La Liga")
        make_fixture(db, status="NS", league_id=a.id)
        make_fixture(db, status="FT", home_goals=1, away_goals=0, league_id=a.id)
        make_fixture(db, status="NS", league_id=b.id)

        assert count_non_started_fixtures_by_league(db, a.id) == 1


class TestGetActiveLeagues:
    def test_returns_only_active(self, db: Session) -> None:
        make_league(db, rapid_api_id=39, active=True)
        make_league(db, rapid_api_id=140, name="La Liga", active=False)

        result = get_active_leagues(db)
        assert [league.rapid_api_id for league in result] == [39]
