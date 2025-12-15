from decimal import Decimal
from sqlalchemy.orm import Session
from sqlalchemy import select, or_

from ..models import (
    Bet,
    Fixture,
    User,
    FixtureResult,
    TransactionRecord,
    TransactionType,
    UserStatus,
)
from ..utils.logging import logger
from ..settings import NOT_STARTED_STATUSES


class ClientSideError(Exception):
    pass


def get_user(db: Session, user_id: str):
    try:
        return db.query(User).filter(User.id == user_id).first()
    except Exception as e:
        logger.error(f"Error fetching user {user_id}: {e}")
        return None


def get_user_by_cognito_id(db: Session, cognito_uuid: str) -> User | None:
    try:
        return db.query(User).filter(User.cognito_uuid == cognito_uuid).first()
    except Exception as e:
        logger.error(f"Error fetching user by cognito_uuid {cognito_uuid}: {e}")
        return None


def get_or_create_user(db: Session, cognito_uuid: str, email: str) -> User | None:
    try:
        user = get_user_by_cognito_id(db, cognito_uuid)

        if not user:
            user = User(
                cognito_uuid=cognito_uuid,
                email=email,
                status=UserStatus.ACTIVE.value,
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            logger.info(f"Created new user: {email} ({cognito_uuid})")

        return user
    except Exception as e:
        db.rollback()
        logger.error(f"Error getting or creating user {email}: {e}")
        return None


def fetch_non_started_fixtures_with_odds(
    db: Session, search: str | None = None
) -> list[Fixture]:

    try:
        query = db.query(Fixture).filter(
            Fixture.status.in_(NOT_STARTED_STATUSES),
            Fixture.home_odds.isnot(None),
            Fixture.away_odds.isnot(None),
            Fixture.draw_odds.isnot(None),
        )

        if search:
            pattern = f"%{search}%"
            query = query.filter(
                or_(
                    Fixture.home_team.ilike(pattern),
                    Fixture.away_team.ilike(pattern),
                    Fixture.venue.ilike(pattern),
                )
            )

        return query.order_by(Fixture.kick_off.asc()).limit(30).all()
    except Exception as e:
        logger.error(f"Error fetching non-started fixtures with odds: {e}")
        return []


def get_user_bets(
    db: Session,
    user_id: str,
    outcome: str | None = None,
    search: str | None = None,
    limit: int | None = 30,
):
    try:
        stmt = (
            select(
                Bet.id.label("id"),
                Bet.user_id.label("user_id"),
                Bet.fixture_id.label("fixture_id"),
                Fixture.home_team.label("home_team"),
                Fixture.away_team.label("away_team"),
                Fixture.kick_off.label("kick_off"),
                Bet.choice.label("choice"),
                Bet.stake.label("stake"),
                Bet.returns.label("returns"),
                Bet.outcome.label("outcome"),
                Bet.created_at.label("created_at"),
            )
            .join(Fixture, Fixture.id == Bet.fixture_id)
            .where(Bet.user_id == user_id)
        )

        if outcome:
            stmt = stmt.where(Bet.outcome == outcome)

        if search:
            pattern = f"%{search}%"
            stmt = stmt.where(
                or_(
                    Fixture.home_team.ilike(pattern),
                    Fixture.away_team.ilike(pattern),
                    Fixture.venue.ilike(pattern),
                )
            )

        stmt = stmt.order_by(Bet.created_at.desc())

        if limit:
            stmt = stmt.limit(limit)

        rows = db.execute(stmt).mappings().all()
        return rows

    except Exception as e:
        logger.error(f"Error fetching bets for user {user_id}: {e}")
        return []


def create_bet(
    db: Session,
    user: User,
    fixture_id: str,
    choice: FixtureResult,
    stake: Decimal,
):
    try:
        fixture = db.query(Fixture).filter(Fixture.id == fixture_id).first()
        if not fixture or not fixture.has_odds:
            raise ClientSideError("Invalid fixture or fixture does not have odds")

        if fixture.status not in NOT_STARTED_STATUSES:
            raise ClientSideError("Fixture has already started")

        if user.balance < stake:
            raise ClientSideError("Insufficient funds")

        odds_map = {
            FixtureResult.HOME: fixture.home_odds,
            FixtureResult.AWAY: fixture.away_odds,
            FixtureResult.DRAW: fixture.draw_odds,
        }

        odds = odds_map.get(choice)
        returns = (stake * odds) + stake

        bet = Bet(
            user_id=user.id,
            fixture_id=fixture.id,
            choice=choice.value,
            stake=stake,
            returns=returns,
        )

        balance_before = user.balance
        user.balance -= stake

        transaction = TransactionRecord(
            bet=bet,
            type=TransactionType.BET.value,
            user_balance_before=balance_before,
            user_balance_after=user.balance,
        )

        db.add(bet)
        db.add(transaction)
        db.commit()

        return {"id": bet.id, "returns": bet.returns}

    except Exception as e:
        db.rollback()
        logger.error(f"Error creating bet: {e}")
        raise
