import requests
from typing import List

from .schemas.fixture import (
    RapidApiFixturesResponse,
    RapidApiUpdateFixturesResponse,
    Fixture,
    UpdateFixture,
)
from .schemas.league import League, RapidApiLeaguesResponse
from .schemas.odds import RapidApiOddsResponse, Odds
from ..settings import RAPID_API_KEY
from ..utils.logging import logger

BASE_URL = "https://v3.football.api-sports.io/"
HEADERS = {
    "x-rapidapi-key": RAPID_API_KEY,
    "x-rapidapi-host": "api-football-v1.p.rapidapi.com",
}


def fetch_leagues() -> list[League]:
    try:
        url = f"{BASE_URL}leagues"
        response = requests.get(url, headers=HEADERS)
        if response.status_code != 200 or response.json()["errors"]:
            raise Exception(
                f"Error fetching leagues: {response.status_code} - {response.text}"
            )
        leagues = RapidApiLeaguesResponse(**response.json()).data
        logger.info(f"Fetched {len(leagues)} leagues")
        return leagues
    except Exception:
        logger.exception("Exception in fetch_leagues")
        return []


def fetch_fixtures_by_league(league_id: int, next: int = 20) -> list[Fixture]:
    try:
        url = f"{BASE_URL}fixtures?league={league_id}&next={next}"
        response = requests.get(url, headers=HEADERS)
        if response.status_code != 200 or response.json()["errors"]:
            raise Exception(
                f"Error fetching fixtures: {response.status_code} - {response.text}"
            )
        fixtures = RapidApiFixturesResponse(**response.json()).data
        logger.info(f"Fetched {len(fixtures)} fixtures for league {league_id}")
        return fixtures
    except Exception:
        # External API boundary: a 3rd-party blip should fail-soft so the job
        # retries next tick rather than crashing the run. logger.exception keeps
        # the traceback for observability.
        logger.exception("Exception in fetch_fixtures_by_league")
        return []


def fetch_odds_by_fixture(fixture_id: int) -> Odds | None:
    try:
        url = f"{BASE_URL}odds?fixture={fixture_id}&bet=1"
        response = requests.get(url, headers=HEADERS)
        if response.status_code != 200 or response.json()["errors"]:
            raise Exception(
                f"Error fetching odds for fixture {fixture_id}: {response.status_code} - {response.text}"
            )
        odds = RapidApiOddsResponse(**response.json()).first_complete_odds()
        return odds
    except Exception:
        logger.exception("Exception in fetch_odds_by_fixture")
        return None


def fetch_fixture_updates(fixture_ids: List[int]) -> list[UpdateFixture]:
    try:
        if not fixture_ids:
            return []
        ids_param = "-".join(map(str, fixture_ids))
        url = f"{BASE_URL}fixtures?ids={ids_param}"
        response = requests.get(url, headers=HEADERS)
        if response.status_code != 200 or response.json()["errors"]:
            raise Exception(
                f"Error fetching fixture updates for ids {ids_param}: {response.status_code} - {response.text}"
            )
        fixture_updates = RapidApiUpdateFixturesResponse(**response.json()).data
        return fixture_updates
    except Exception:
        logger.exception("Exception in fetch_fixture_updates")
        return []
