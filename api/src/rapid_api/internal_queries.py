from typing import Protocol, Sequence

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
)


class HasToDbDict(Protocol):
    def to_db_dict(self) -> dict[str, object] | None: ...


def get_active_league_rapid_id(db: Session) -> int | None:
    try:
        league = db.query(League).filter(League.active.is_(True)).first()
        return league.rapid_api_id if league else None
    except Exception as e:
        logger.error(f"Error fetching active league: {e}")
        return None


def fetch_non_started_fixtures(db: Session) -> list[Fixture]:
    try:
        fixtures = (
            db.query(Fixture).filter(Fixture.status.in_(NOT_STARTED_STATUSES)).all()
        )
        return fixtures
    except Exception as e:
        logger.error(f"Error fetching non-started fixtures: {e}")
        return []


def fetch_non_finished_fixtures(db: Session) -> list[Fixture]:
    try:
        return (
            db.query(Fixture)
            .filter(~Fixture.status.in_(FINISHED_STATUSES))
            .order_by(Fixture.kick_off.asc())
            .limit(20)
            .all()
        )
    except Exception as e:
        logger.error(f"Error fetching non-finished fixtures: {e}")
        return []


def save_new_fixtures(db: Session, fixtures: list[FixtureSchema]) -> None:
    try:
        if not fixtures:
            return

        new_fixtures = []
        for f in fixtures:
            existing = db.query(Fixture).filter_by(rapid_api_id=f.info.id).first()
            if existing:
                continue
            new_fixtures.append(f)

        rows = [f.to_db_dict() for f in new_fixtures]
        if rows:
            logger.info(f"Saving {len(rows)} new fixtures to the database.")
            db.execute(insert(Fixture), rows)
            db.commit()
        else:
            logger.info("No new fixtures to save.")
    except Exception as e:
        logger.error(f"Error saving new fixtures: {e}")
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
    except Exception as e:
        logger.error(f"Error fetching fixtures missing odds: {e}")
        return []


def update_fixtures(db: Session, fixture_updates: Sequence[HasToDbDict]) -> None:
    try:
        rows = [
            row for row in (f.to_db_dict() for f in fixture_updates) if row is not None
        ]
        if not rows:
            return
        db.execute(update(Fixture), rows)
        db.commit()
    except Exception as e:
        logger.error(f"Error updating fixtures: {e}")
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
    except Exception as e:
        logger.error(f"Error fetching bets to settle: {e}")
        return []


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
    except Exception as e:
        logger.error(f"Error fetching voided bets to settle: {e}")
        return []


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

    except Exception as e:
        db.rollback()
        logger.error(f"Error settling bet {bet.id}: {e}")
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

    except Exception as e:
        db.rollback()
        logger.error(f"Error settling voided bet {bet.id}: {e}")
        raise
