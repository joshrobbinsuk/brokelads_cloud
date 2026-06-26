"""Contract tests for GET /client/fixture (league filter + nested league shape,
money fields as strings) and GET /client/league (active-only)."""

from typing import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.client.routes import router as client_router
from src.client.utils.cognito import verify_token
from src.database import get_db
from src.tests.factories import make_fixture, make_league


@pytest.fixture()
def client(db: Session) -> Iterator[TestClient]:
    app = FastAPI()
    app.include_router(client_router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[verify_token] = lambda: {"sub": "test"}
    with TestClient(app) as test_client:
        yield test_client


class TestGetFixtures:
    def test_nested_league_and_string_odds(
        self, client: TestClient, db: Session
    ) -> None:
        league = make_league(db, name="Premier League", display_name="EPL")
        make_fixture(db, status="NS", league_id=league.id)

        body = client.get("/client/fixture").json()

        assert len(body["fixtures"]) == 1
        fixture = body["fixtures"][0]
        assert fixture["league"] == {
            "id": league.id,
            "display_name": "EPL",
            "logo": "league.png",
        }
        # Money crosses the wire as strings.
        assert fixture["home_odds"] == "2.00"
        assert isinstance(fixture["away_odds"], str)

    def test_null_league_when_unlinked(self, client: TestClient, db: Session) -> None:
        make_fixture(db, status="NS", league_id=None)
        body = client.get("/client/fixture").json()
        assert body["fixtures"][0]["league"] is None

    def test_league_id_filter(self, client: TestClient, db: Session) -> None:
        epl = make_league(db, rapid_api_id=39, name="EPL")
        laliga = make_league(db, rapid_api_id=140, name="La Liga")
        make_fixture(db, status="NS", league_id=epl.id)
        make_fixture(db, status="NS", league_id=laliga.id)

        body = client.get(f"/client/fixture?league_id={epl.id}").json()

        assert len(body["fixtures"]) == 1
        assert body["fixtures"][0]["league"]["id"] == epl.id


class TestGetLeagues:
    def test_returns_active_only(self, client: TestClient, db: Session) -> None:
        active = make_league(db, rapid_api_id=39, name="EPL", active=True)
        make_league(db, rapid_api_id=140, name="La Liga", active=False)

        body = client.get("/client/league").json()

        assert body["leagues"] == [
            {"id": active.id, "display_name": "EPL", "logo": "league.png"}
        ]
