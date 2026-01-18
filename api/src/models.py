from enum import Enum
from datetime import datetime, timedelta, timezone
from typing import cast

from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    Numeric,
    Boolean,
    ForeignKey,
)
from sqlalchemy.orm import relationship, validates

from src.database import BaseModel
from .settings import OUTCOME_STATUSES


class UserStatus(str, Enum):
    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"
    INVITED = "INVITED"


class FixtureResult(str, Enum):
    HOME = "HOME"
    AWAY = "AWAY"
    DRAW = "DRAW"


class BetOutcome(str, Enum):
    UNDECIDED = "UNDECIDED"
    WON = "WON"
    LOST = "LOST"
    VOIDED = "VOIDED"


class TransactionType(str, Enum):
    BET = "BET"
    PAYOUT_BET_WON = "WON"
    PAYOUT_BET_VOIDED = "VOID"


class User(BaseModel):
    __tablename__ = "user"

    status = Column(String(16), default=UserStatus.ACTIVE.value, nullable=False)
    cognito_uuid = Column(String(64), nullable=False, index=True)
    email = Column(String, unique=True, nullable=False)
    balance = Column(Numeric(19, 2), default=100.00, nullable=False)

    # Relationships
    bets = relationship("Bet", back_populates="user")

    @property
    def is_authenticated(self) -> bool:
        return True

    @validates("status")
    def validate_status(self, key: str, value: str) -> str:
        allowed = {e.value for e in UserStatus}
        if value not in allowed:
            raise ValueError(f"Invalid user status: {value}")
        return value

    def __str__(self) -> str:
        return cast(str, self.email)


class League(BaseModel):
    __tablename__ = "league"

    rapid_api_id = Column(Integer, nullable=False)
    name = Column(String(255), nullable=False)
    display_name = Column(String(255), nullable=False)
    active = Column(Boolean, default=False, nullable=False)

    def __str__(self) -> str:
        return cast(str, self.name)


class Fixture(BaseModel):
    __tablename__ = "fixture"

    status = Column(String(5), nullable=False)
    rapid_api_id = Column(Integer, nullable=False)
    kick_off = Column(DateTime(timezone=True), nullable=False)
    venue = Column(String(255), nullable=False)
    home_team = Column(String(255), nullable=False)
    home_team_logo = Column(String(255), nullable=False)
    away_team = Column(String(255), nullable=False)
    away_team_logo = Column(String(255), nullable=False)
    home_odds = Column(Numeric(5, 2), nullable=True)
    away_odds = Column(Numeric(5, 2), nullable=True)
    draw_odds = Column(Numeric(5, 2), nullable=True)
    home_goals = Column(Integer, nullable=True)
    away_goals = Column(Integer, nullable=True)

    # Relationships
    bets = relationship("Bet", back_populates="fixture")

    def __str__(self) -> str:
        return f"{self.home_team} v {self.away_team}"

    @property
    def has_odds(self) -> bool:
        return (
            (self.home_odds is not None)
            and (self.away_odds is not None)
            and (self.draw_odds is not None)
        )

    @property
    def outcome(self) -> str | None:
        if (
            self.home_goals is None
            or self.away_goals is None
            or self.status not in OUTCOME_STATUSES
        ):
            return None
        if self.home_goals > self.away_goals:
            return FixtureResult.HOME.value
        elif self.home_goals < self.away_goals:
            return FixtureResult.AWAY.value
        else:
            return FixtureResult.DRAW.value


class Bet(BaseModel):
    __tablename__ = "bet"

    fixture_id = Column(String(36), ForeignKey("fixture.id"), nullable=False)
    user_id = Column(String(36), ForeignKey("user.id"), nullable=False)
    choice = Column(String(5), nullable=False)
    stake = Column(Numeric(5, 2), nullable=False)
    returns = Column(Numeric(5, 2), nullable=False)
    outcome = Column(String(10), default=BetOutcome.UNDECIDED.value, nullable=False)

    # Relationships
    fixture = relationship("Fixture", back_populates="bets")
    user = relationship("User", back_populates="bets")
    transaction_records = relationship("TransactionRecord", back_populates="bet")

    @validates("choice")
    def validate_choice(self, key: str, value: str) -> str:
        allowed = {e.value for e in FixtureResult}
        if value not in allowed:
            raise ValueError(f"Invalid bet choice: {value}")
        return value

    @validates("outcome")
    def validate_outcome(self, key: str, value: str) -> str:
        allowed = {e.value for e in BetOutcome}
        if value not in allowed:
            raise ValueError(f"Invalid bet outcome: {value}")
        return value


class TransactionRecord(BaseModel):
    __tablename__ = "transaction_record"

    type = Column(String(6), nullable=False)
    bet_id = Column(String(36), ForeignKey("bet.id"), nullable=False)
    user_balance_before = Column(Numeric(5, 2), nullable=False)
    user_balance_after = Column(Numeric(5, 2), nullable=False)

    # Relationships
    bet = relationship("Bet", back_populates="transaction_records")

    @validates("type")
    def validate_type(self, key: str, value: str) -> str:
        allowed = {e.value for e in TransactionType}
        if value not in allowed:
            raise ValueError(f"Invalid transaction type: {value}")
        return value


class JobControl(BaseModel):
    __tablename__ = "job_control"

    job_name = Column(String(64), unique=True, nullable=False, index=True)
    enabled = Column(Boolean, default=True, nullable=False)
    min_interval_seconds = Column(Integer, default=300, nullable=False)

    last_run_at = Column(DateTime(timezone=True), nullable=True)

    def is_due(self) -> bool:
        enabled = cast(bool, self.enabled)
        if not enabled:
            return False

        last_run_at = cast(datetime | None, self.last_run_at)
        if last_run_at is None:
            return True

        return datetime.now(timezone.utc) >= last_run_at + timedelta(
            seconds=cast(int, self.min_interval_seconds)
        )

    def __str__(self) -> str:
        return f"{self.job_name} (enabled={self.enabled}, interval={self.min_interval_seconds}s)"
