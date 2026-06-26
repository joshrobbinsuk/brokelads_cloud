from typing import Sequence

from sqlalchemy import insert, update
from sqlalchemy.orm import Session, joinedload


from ..models import (
    Fixture,
    League,
    Bet,
    BetOutcome,
    User,
    TransactionRecord,
    TransactionType,
)
from ..utils.logging import logger
from ..settings import (
    NOT_STARTED_STATUSES,
    FINISHED_STATUSES,
    OUTCOME_STATUSES,
    VOIDED_STATUSES,
)

from .schemas.fixture import (
    Fixture as FixtureSchema,
    UpdateFixture as UpdateFixtureSchema,
)
from .schemas.league import League as LeagueSchema
from .schemas.odds import Odds as OddsSchema


def get_active_leagues(db: Session) -> list[League]:
    try:
        return db.query(League).filter(League.active.is_(True)).all()
    except Exception:
        logger.exception("Error fetching active leagues")
        raise


def count_non_started_fixtures_by_league(db: Session, league_id: str) -> int:
    try:
        return (
            db.query(Fixture)
            .filter(
                Fixture.league_id == league_id,
                Fixture.status.in_(NOT_STARTED_STATUSES),
            )
            .count()
        )
    except Exception:
        logger.exception("Error counting non-started fixtures by league")
        raise


def upsert_leagues(db: Session, leagues: list[LeagueSchema]) -> None:
    try:
        if not leagues:
            return

        existing_by_rapid_id = {
            league.rapid_api_id: league for league in db.query(League).all()
        }

        new_rows = []
        for league in leagues:
            row = league.to_db_dict()
            existing = existing_by_rapid_id.get(row["rapid_api_id"])
            if existing:
                # Refresh metadata only — never touch `active` so admin toggles
                # survive in-place deploys.
                existing.name = row["name"]
                existing.type = row["type"]
                existing.logo = row["logo"]
                existing.country = row["country"]
            else:
                new_rows.append({**row, "active": False})

        if new_rows:
            db.execute(insert(League), new_rows)
        db.commit()
        logger.info(
            f"Upserted leagues: {len(new_rows)} inserted, "
            f"{len(leagues) - len(new_rows)} refreshed."
        )
    except Exception:
        db.rollback()
        logger.exception("Error upserting leagues")
        raise


def fetch_non_started_fixtures(db: Session) -> list[Fixture]:
    try:
        fixtures = (
            db.query(Fixture).filter(Fixture.status.in_(NOT_STARTED_STATUSES)).all()
        )
        return fixtures
    except Exception:
        logger.exception("Error fetching non-started fixtures")
        raise


def fetch_non_finished_fixtures(db: Session) -> list[Fixture]:
    try:
        return (
            db.query(Fixture)
            .filter(~Fixture.status.in_(FINISHED_STATUSES))
            .order_by(Fixture.kick_off.asc())
            .limit(20)
            .all()
        )
    except Exception:
        logger.exception("Error fetching non-finished fixtures")
        raise


def save_new_fixtures(
    db: Session, fixtures: list[FixtureSchema], league_id: str | None = None
) -> None:
    try:
        if not fixtures:
            return

        new_fixtures = []
        backfilled = 0
        for f in fixtures:
            existing = db.query(Fixture).filter_by(rapid_api_id=f.info.id).first()
            if existing:
                # Heal pre-existing leagueless rows in place so there is exactly
                # one row per match and old fixtures gain their league.
                if existing.league_id is None and league_id is not None:
                    existing.league_id = league_id
                    backfilled += 1
                continue
            new_fixtures.append(f)

        rows = [{**f.to_db_dict(), "league_id": league_id} for f in new_fixtures]
        if rows:
            logger.info(f"Saving {len(rows)} new fixtures to the database.")
            db.execute(insert(Fixture), rows)

        if rows or backfilled:
            logger.info(f"Backfilled league_id on {backfilled} existing fixtures.")
            db.commit()
        else:
            logger.info("No new fixtures to save.")
    except Exception:
        logger.exception("Error saving new fixtures")
        raise


def fetch_fixtures_missing_odds(db: Session, limit: int = 50) -> list[Fixture]:
    try:
        return (
            db.query(Fixture)
            .filter(
                Fixture.home_odds.is_(None),
                Fixture.away_odds.is_(None),
                Fixture.draw_odds.is_(None),
            )
            .order_by(Fixture.kick_off.asc())
            .limit(limit)
            .all()
        )
    except Exception:
        logger.exception("Error fetching fixtures missing odds")
        raise


def update_fixtures(
    db: Session, fixture_updates: Sequence[UpdateFixtureSchema | OddsSchema]
) -> None:
    try:
        rows = [
            row for row in (f.to_db_dict() for f in fixture_updates) if row is not None
        ]
        if not rows:
            return
        db.execute(update(Fixture), rows)
        db.commit()
    except Exception:
        logger.exception("Error updating fixtures")
        raise


def fetch_bets_to_settle(db: Session, limit: int = 200) -> list[Bet]:
    try:
        return (
            db.query(Bet)
            .options(joinedload(Bet.fixture))
            .join(Fixture, Bet.fixture_id == Fixture.id)
            .filter(
                Bet.outcome == BetOutcome.UNDECIDED.value,
                Fixture.status.in_(OUTCOME_STATUSES),
            )
            .order_by(Fixture.kick_off.asc(), Bet.created_at.asc())
            .limit(limit)
            .all()
        )
    except Exception:
        logger.exception("Error fetching bets to settle")
        raise


def fetch_voided_bets_to_settle(db: Session, limit: int = 200) -> list[Bet]:
    try:
        return (
            db.query(Bet)
            .options(joinedload(Bet.fixture))
            .filter(
                Bet.outcome == BetOutcome.UNDECIDED.value,
                Bet.fixture.has(Fixture.status.in_(VOIDED_STATUSES)),
            )
            .order_by(Bet.created_at.asc())
            .limit(limit)
            .all()
        )
    except Exception:
        logger.exception("Error fetching voided bets to settle")
        raise


def settle_bet(db: Session, bet: Bet, won: bool) -> None:
    try:
        if bet.outcome != BetOutcome.UNDECIDED.value:
            raise Exception(f"Bet {bet.id} has already been settled.")
        user = db.query(User).filter(User.id == bet.user_id).first()
        if user is None:
            raise Exception(f"User {bet.user_id} not found for bet {bet.id}.")
        if won:
            bet.outcome = BetOutcome.WON.value
            balance_before = user.balance
            user.balance = balance_before + bet.returns

            transaction = TransactionRecord(
                bet_id=bet.id,
                type=TransactionType.PAYOUT_BET_WON.value,
                user_balance_before=balance_before,
                user_balance_after=user.balance,
            )
            db.add(transaction)
        else:
            bet.outcome = BetOutcome.LOST.value

        db.commit()

    except Exception:
        db.rollback()
        logger.exception(f"Error settling bet {bet.id}")
        raise


def settle_voided_bet(db: Session, bet: Bet) -> None:
    try:
        if bet.outcome != BetOutcome.UNDECIDED.value:
            raise Exception(f"Bet {bet.id} has already been settled.")
        user = db.query(User).filter(User.id == bet.user_id).first()
        if user is None:
            raise Exception(f"User {bet.user_id} not found for bet {bet.id}.")
        bet.outcome = BetOutcome.VOIDED.value
        payout = bet.stake

        balance_before = user.balance
        user.balance = balance_before + payout

        transaction = TransactionRecord(
            bet_id=bet.id,
            type=TransactionType.PAYOUT_BET_VOIDED.value,
            user_balance_before=balance_before,
            user_balance_after=user.balance,
        )

        db.add(transaction)
        db.commit()

    except Exception:
        db.rollback()
        logger.exception(f"Error settling voided bet {bet.id}")
        raise
