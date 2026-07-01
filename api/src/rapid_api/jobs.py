from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..utils.logging import logger
from ..settings import N_FIXTURES_PER_LEAGUE

from .external_calls import (
    fetch_leagues,
    fetch_fixtures_by_league,
    fetch_odds_by_fixture,
    fetch_fixture_updates,
)
from .internal_queries import (
    get_active_leagues,
    count_non_started_fixtures_by_league,
    upsert_leagues,
    fetch_non_finished_fixtures,
    save_new_fixtures,
    fetch_fixtures_missing_odds,
    update_fixtures,
    fetch_bets_to_settle,
    fetch_voided_bets_to_settle,
    settle_bet,
    settle_voided_bet,
    fetch_cups_to_close,
    fetch_cup_backstop_bets,
    count_undecided_bets_in_cup,
    settle_cup,
    mark_cup_closing,
)


def run_fetch_leagues(db: Session) -> None:
    upsert_leagues(db, fetch_leagues())


def run_fetch_fixtures(db: Session) -> None:
    leagues = get_active_leagues(db)
    if not leagues:
        logger.warning("No active leagues found. Skipping fixture fetch.")
        return

    for league in leagues:
        count = count_non_started_fixtures_by_league(db, league.id)
        if count >= N_FIXTURES_PER_LEAGUE:
            logger.info(f"League {league.name} at target ({count}). Skipping fetch.")
            continue

        fixtures = fetch_fixtures_by_league(
            league_id=league.rapid_api_id, next=N_FIXTURES_PER_LEAGUE
        )
        save_new_fixtures(db, fixtures, league_id=league.id)


def run_fetch_odds(db: Session) -> None:
    fixtures = fetch_fixtures_missing_odds(db)
    rapid_id_to_id_map = {f.rapid_api_id: f.id for f in fixtures}
    new_odds = []
    for rapid_id in list(rapid_id_to_id_map.keys()):
        odds = fetch_odds_by_fixture(fixture_id=rapid_id)
        if odds:
            odds.bl_id = rapid_id_to_id_map.get(rapid_id)
            new_odds.append(odds)
    update_fixtures(db, new_odds)


def run_fetch_fixture_updates(db: Session) -> None:
    fixtures = fetch_non_finished_fixtures(db)
    rapid_id_to_id_map = {f.rapid_api_id: f.id for f in fixtures}
    updates = fetch_fixture_updates(list(rapid_id_to_id_map.keys()))

    if not updates:
        logger.info("No fixture updates fetched.")
        return

    for update in updates:
        update.bl_id = rapid_id_to_id_map.get(update.info.id)
    update_fixtures(db, updates)


def run_settle_bets(db: Session) -> None:
    bets = fetch_bets_to_settle(db)
    for bet in bets:
        fixture = bet.fixture
        won = fixture.outcome == bet.choice
        try:
            settle_bet(db, bet=bet, won=won)
        except Exception as e:
            logger.error(f"Error settling bet {bet.id}: {e}")


def run_settle_voided_bets(db: Session) -> None:
    bets = fetch_voided_bets_to_settle(db)
    for bet in bets:
        try:
            settle_voided_bet(db, bet=bet)
        except Exception as e:
            logger.error(f"Error settling voided bet {bet.id}: {e}")


def run_close_cups(db: Session) -> None:
    now = datetime.now(timezone.utc)
    cups = fetch_cups_to_close(db, now)
    if not cups:
        return

    # (1) Resolve everything the normal settlement path can — finished fixtures
    #     (win/lose) and explicitly-voided ones (refund) — before deciding
    #     whether each cup can terminate.
    run_settle_bets(db)
    run_settle_voided_bets(db)

    for cup in cups:
        mark_cup_closing(db, cup)

        # (2) Backstop: force-void bets whose fixture kicked off long ago but
        #     whose status never resolved (stuck LIVE/SUSP/etc.) so the cup can
        #     terminate rather than wait forever.
        for bet in fetch_cup_backstop_bets(db, cup, now):
            try:
                settle_voided_bet(db, bet=bet)
            except Exception as e:
                logger.error(f"Error force-voiding stuck bet {bet.id}: {e}")

        # (3) Only crown winners once no bets are still live.
        if count_undecided_bets_in_cup(db, cup) == 0:
            settle_cup(db, cup)


JOB_REGISTRY = {
    "fetch_leagues": run_fetch_leagues,
    "fetch_fixtures": run_fetch_fixtures,
    "fetch_odds": run_fetch_odds,
    "fetch_fixture_updates": run_fetch_fixture_updates,
    "settle_bets": run_settle_bets,
    "settle_voided_bets": run_settle_voided_bets,
    "close_cups": run_close_cups,
}
