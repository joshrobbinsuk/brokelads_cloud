"""User provisioning and the user-facing read queries (client.queries)."""

import pytest
from sqlalchemy.orm import Session

from src.database import BaseModel
from src.models import BetOutcome, FixtureResult, User, UserStatus
from src.client.queries import (
    fetch_non_started_fixtures_with_odds,
    get_or_create_user,
    get_user_bets,
)
from src.tests.factories import make_bet, make_fixture, make_league, make_user


class TestGetOrCreateUser:
    def test_creates_active_user_on_first_call(self, db: Session) -> None:
        user = get_or_create_user(db, auth_uid="abc-123", email="new@test.com")

        assert user is not None
        assert user.email == "new@test.com"
        assert user.auth_uid == "abc-123"
        assert user.status == UserStatus.ACTIVE.value
        assert db.query(User).count() == 1

    def test_returns_existing_user_without_duplicating(self, db: Session) -> None:
        first = get_or_create_user(db, auth_uid="abc-123", email="new@test.com")
        second = get_or_create_user(db, auth_uid="abc-123", email="new@test.com")

        assert first is not None and second is not None
        assert first.id == second.id
        assert db.query(User).count() == 1

    def test_reraises_on_db_error_rather_than_swallowing(self, db: Session) -> None:
        # A DB fault must propagate, not surface as a misleading "no user".
        BaseModel.metadata.drop_all(bind=db.get_bind())
        with pytest.raises(Exception):
            get_or_create_user(db, auth_uid="abc-123", email="new@test.com")


class TestFetchNonStartedFixturesWithOdds:
    def test_returns_not_started_with_complete_odds(self, db: Session) -> None:
        league = make_league(db)
        make_fixture(db, status="NS", league_id=league.id)  # has odds by default
        result = fetch_non_started_fixtures_with_odds(db)
        assert len(result) == 1

    def test_excludes_started_fixtures(self, db: Session) -> None:
        league = make_league(db)
        make_fixture(db, status="FT", home_goals=1, away_goals=0, league_id=league.id)
        assert fetch_non_started_fixtures_with_odds(db) == []

    def test_excludes_fixtures_missing_any_odd(self, db: Session) -> None:
        league = make_league(db)
        make_fixture(db, status="NS", draw_odds=None, league_id=league.id)
        assert fetch_non_started_fixtures_with_odds(db) == []

    def test_excludes_leagueless_fixtures(self, db: Session) -> None:
        make_fixture(db, status="NS", league_id=None)
        assert fetch_non_started_fixtures_with_odds(db) == []

    def test_search_matches_team_name(self, db: Session) -> None:
        league = make_league(db)
        make_fixture(db, status="NS", league_id=league.id)  # Home FC v Away FC
        result = fetch_non_started_fixtures_with_odds(db, search="home")
        assert len(result) == 1
        assert fetch_non_started_fixtures_with_odds(db, search="nomatch") == []


class TestGetUserBets:
    def test_returns_only_the_users_own_bets(self, db: Session) -> None:
        owner = make_user(db, email="owner@test.com", auth_uid="owner")
        other = make_user(db, email="other@test.com", auth_uid="other")
        fixture = make_fixture(db, status="FT", home_goals=1, away_goals=0)
        make_bet(db, user=owner, fixture=fixture)
        make_bet(db, user=other, fixture=fixture)

        rows = get_user_bets(db, owner.id)
        assert len(rows) == 1
        assert rows[0]["user_id"] == owner.id
        # The join surfaces fixture fields onto each row.
        assert rows[0]["home_team"] == "Home FC"

    def test_outcome_filter(self, db: Session) -> None:
        user = make_user(db)
        fixture = make_fixture(db, status="FT", home_goals=1, away_goals=0)
        make_bet(db, user=user, fixture=fixture, outcome=BetOutcome.WON.value)
        make_bet(db, user=user, fixture=fixture, outcome=BetOutcome.LOST.value)

        rows = get_user_bets(db, user.id, outcome=BetOutcome.WON.value)
        assert len(rows) == 1
        assert rows[0]["outcome"] == BetOutcome.WON.value

    def test_search_filters_by_fixture_team(self, db: Session) -> None:
        user = make_user(db)
        arsenal = make_fixture(db, status="FT", home_goals=1, away_goals=0)
        arsenal.home_team = "Arsenal"
        db.commit()
        spurs = make_fixture(db, status="FT", home_goals=0, away_goals=1)
        spurs.home_team = "Spurs"
        db.commit()
        make_bet(db, user=user, fixture=arsenal)
        make_bet(db, user=user, fixture=spurs)

        rows = get_user_bets(db, user.id, search="arsenal")
        assert len(rows) == 1
        assert rows[0]["home_team"] == "Arsenal"

    def test_limit_caps_results(self, db: Session) -> None:
        user = make_user(db)
        fixture = make_fixture(db, status="FT", home_goals=1, away_goals=0)
        make_bet(db, user=user, fixture=fixture, choice=FixtureResult.HOME)
        make_bet(db, user=user, fixture=fixture, choice=FixtureResult.AWAY)

        assert len(get_user_bets(db, user.id, limit=1)) == 1
