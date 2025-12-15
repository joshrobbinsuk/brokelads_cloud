from ..utils.logging import logger
from ..settings import N_NOT_STARTED_FIXTURES_TO_STORE

from .external_calls import (
    fetch_fixtures_by_league,
    fetch_odds_by_fixture,
    fetch_fixture_updates,
)
from .internal_queries import (
    get_active_league_rapid_id,
    fetch_non_started_fixtures,
    fetch_non_finished_fixtures,
    save_new_fixtures,
    fetch_fixtures_missing_odds,
    update_fixtures,
    fetch_bets_to_settle,
    fetch_voided_bets_to_settle,
    settle_bet,
    settle_voided_bet,
)


def run_fetch_fixtures(db):
    league_id = get_active_league_rapid_id(db)
    if not league_id:
        logger.warning("No active league found. Skipping fixture fetch.")
        return
    not_started_fixtures = fetch_non_started_fixtures(db)
    if N_NOT_STARTED_FIXTURES_TO_STORE - len(not_started_fixtures) > 0:
        fixtures = fetch_fixtures_by_league(
            league_id=league_id, next=N_NOT_STARTED_FIXTURES_TO_STORE
        )
        save_new_fixtures(db, fixtures)
    else:
        logger.info("Sufficient non-started fixtures in DB. Skipping fetch.")


def run_fetch_odds(db):
    fixtures = fetch_fixtures_missing_odds(db)
    rapid_id_to_id_map = {f.rapid_api_id: f.id for f in fixtures}
    new_odds = []
    for rapid_id in rapid_id_to_id_map.keys():
        odds = fetch_odds_by_fixture(fixture_id=rapid_id)
        if odds:
            odds.bl_id = rapid_id_to_id_map.get(rapid_id)
            new_odds.append(odds)
    update_fixtures(db, new_odds)


def run_fetch_fixture_updates(db):
    fixtures = fetch_non_finished_fixtures(db)
    rapid_id_to_id_map = {f.rapid_api_id: f.id for f in fixtures}
    updates = fetch_fixture_updates(rapid_id_to_id_map.keys())

    if not updates:
        logger.info("No fixture updates fetched.")
        return

    for update in updates:
        update.bl_id = rapid_id_to_id_map.get(update.info.id)
    update_fixtures(db, updates)


def run_settle_bets(db):
    bets = fetch_bets_to_settle(db)
    for bet in bets:
        fixture = bet.fixture
        won = fixture.outcome == bet.choice
        try:
            settle_bet(db, bet=bet, won=won)
        except Exception as e:
            logger.error(f"Error settling bet {bet.id}: {e}")


def run_settle_voided_bets(db):
    bets = fetch_voided_bets_to_settle(db)
    for bet in bets:
        try:
            settle_voided_bet(db, bet=bet)
        except Exception as e:
            logger.error(f"Error settling voided bet {bet.id}: {e}")


JOB_REGISTRY = {
    "fetch_fixtures": run_fetch_fixtures,
    "fetch_odds": run_fetch_odds,
    "fetch_fixture_updates": run_fetch_fixture_updates,
    "settle_bets": run_settle_bets,
    "settle_voided_bets": run_settle_voided_bets,
}
