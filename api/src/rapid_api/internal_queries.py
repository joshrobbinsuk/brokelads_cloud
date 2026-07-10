from datetime import datetime, timedelta
from typing import Sequence

from sqlalchemy import insert, update
from sqlalchemy.orm import Session, joinedload


from ..models import (
    Fixture,
    League,
    Bet,
    BetOutcome,
    Cup,
    CupEntry,
    CupStatus,
    LedgerEntry,
    LedgerEntryType,
)
from ..utils.logging import logger
from ..settings import (
    NOT_STARTED_STATUSES,
    FINISHED_STATUSES,
    OUTCOME_STATUSES,
    VOIDED_STATUSES,
    CUP_BET_MAX_AGE_HOURS,
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
                Fixture.status.in_(NOT_STARTED_STATUSES),
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


def _entry_for_bet(db: Session, bet: Bet) -> CupEntry:
    return db.query(CupEntry).filter(CupEntry.id == bet.cup_entry_id).one()


def settle_bet(db: Session, bet: Bet, won: bool) -> None:
    try:
        if bet.outcome != BetOutcome.UNDECIDED.value:
            raise Exception(f"Bet {bet.id} has already been settled.")
        entry = _entry_for_bet(db, bet)
        if won:
            bet.outcome = BetOutcome.WON.value
            entry.credit(bet.returns)
            db.add(
                LedgerEntry(
                    cup_entry_id=entry.id,
                    bet_id=bet.id,
                    type=LedgerEntryType.BET_PAYOUT.value,
                    amount=bet.returns,
                    balance_after=entry.balance,
                )
            )
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
        entry = _entry_for_bet(db, bet)
        bet.outcome = BetOutcome.VOIDED.value

        entry.credit(bet.stake)
        db.add(
            LedgerEntry(
                cup_entry_id=entry.id,
                bet_id=bet.id,
                type=LedgerEntryType.BET_VOID_REFUND.value,
                amount=bet.stake,
                balance_after=entry.balance,
            )
        )

        db.commit()

    except Exception:
        db.rollback()
        logger.exception(f"Error settling voided bet {bet.id}")
        raise


def fetch_cups_to_close(db: Session, now: datetime) -> list[Cup]:
    """Cups whose week has ended and which are not yet SETTLED."""
    try:
        return (
            db.query(Cup)
            .filter(Cup.week_end <= now, Cup.status != CupStatus.SETTLED.value)
            .all()
        )
    except Exception:
        logger.exception("Error fetching cups to close")
        raise


def fetch_cup_backstop_bets(db: Session, cup: Cup, now: datetime) -> list[Bet]:
    """Still-UNDECIDED bets in a cup whose fixture kicked off more than
    CUP_BET_MAX_AGE_HOURS ago and is NOT in a finished state — the silent
    non-updates the backstop force-voids. Finished fixtures (OUTCOME_STATUSES)
    are excluded: a finished-but-unsettled bet (e.g. left behind by the
    settle_bets row cap) must be settled as win/lose, never voided."""
    try:
        cutoff = now - timedelta(hours=CUP_BET_MAX_AGE_HOURS)
        return (
            db.query(Bet)
            .options(joinedload(Bet.fixture))
            .join(CupEntry, CupEntry.id == Bet.cup_entry_id)
            .join(Fixture, Fixture.id == Bet.fixture_id)
            .filter(
                CupEntry.cup_id == cup.id,
                Bet.outcome == BetOutcome.UNDECIDED.value,
                Fixture.kick_off <= cutoff,
                Fixture.status.notin_(OUTCOME_STATUSES),
            )
            .all()
        )
    except Exception:
        logger.exception("Error fetching cup backstop bets")
        raise


def count_undecided_bets_in_cup(db: Session, cup: Cup) -> int:
    try:
        return (
            db.query(Bet)
            .join(CupEntry, CupEntry.id == Bet.cup_entry_id)
            .filter(
                CupEntry.cup_id == cup.id,
                Bet.outcome == BetOutcome.UNDECIDED.value,
            )
            .count()
        )
    except Exception:
        logger.exception("Error counting undecided bets in cup")
        raise


def settle_cup(db: Session, cup: Cup) -> None:
    """Stamp each entry's frozen final_rank (competition ranking: ties share a
    rank, co-winners are both rank 1) and the cup's final_entry_count, then mark
    the cup SETTLED. Caller guarantees no UNDECIDED bets remain."""
    try:
        entries = (
            db.query(CupEntry)
            .filter(CupEntry.cup_id == cup.id)
            .order_by(CupEntry.balance.desc())
            .all()
        )
        for entry in entries:
            better = sum(1 for other in entries if other.balance > entry.balance)
            entry.final_rank = better + 1
        cup.final_entry_count = len(entries)
        cup.status = CupStatus.SETTLED.value
        db.commit()
        logger.info(f"Cup {cup.id} settled.")
    except Exception:
        db.rollback()
        logger.exception(f"Error settling cup {cup.id}")
        raise


def mark_cup_closing(db: Session, cup: Cup) -> None:
    try:
        if cup.status == CupStatus.OPEN.value:
            cup.status = CupStatus.CLOSING.value
            db.commit()
    except Exception:
        db.rollback()
        logger.exception(f"Error marking cup {cup.id} closing")
        raise
