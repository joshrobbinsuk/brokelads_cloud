from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from enum import Enum

from sqlalchemy import (
    JSON,
    BigInteger,
    Date,
    Identity,
    Integer,
    String,
    DateTime,
    Numeric,
    Boolean,
    ForeignKey,
    Index,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, Session, mapped_column, relationship, validates

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


class LedgerEntryType(str, Enum):
    ENTRY_GRANT = "ENTRY_GRANT"
    BET_STAKE = "BET_STAKE"
    BET_PAYOUT = "BET_PAYOUT"
    BET_VOID_REFUND = "BET_VOID_REFUND"


class CupStatus(str, Enum):
    OPEN = "OPEN"
    CLOSING = "CLOSING"
    SETTLED = "SETTLED"


class User(BaseModel):
    __tablename__ = "user"
    # Case-insensitive uniqueness as a true DB invariant (not just an app check).
    # lower(NULL) is NULL, so multiple NULL usernames are still allowed.
    __table_args__ = (
        Index("uq_user_username_lower", text("lower(username)"), unique=True),
    )

    status: Mapped[str] = mapped_column(
        String(16), default=UserStatus.ACTIVE.value, nullable=False
    )
    cognito_uuid: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    email: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    # Freely changeable; case-insensitively unique (see the index above). Length
    # limit is enforced at the request boundary (SetUsernameRequest).
    username: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # `<icon>-<colour>` id from the fixed set in settings.AVATAR_IDS. Null = never
    # chosen -> FE renders a fallback disc. Validated at the request boundary
    # (SetAvatarRequest), not here.
    avatar: Mapped[str | None] = mapped_column(String(20), nullable=True)

    bets: Mapped[list["Bet"]] = relationship("Bet", back_populates="user")

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
        return self.email


class League(BaseModel):
    __tablename__ = "league"

    rapid_api_id: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    logo: Mapped[str | None] = mapped_column(String(255), nullable=True)
    country: Mapped[str | None] = mapped_column(String(255), nullable=True)
    type: Mapped[str | None] = mapped_column(String(32), nullable=True)

    def __str__(self) -> str:
        return self.name


class Fixture(BaseModel):
    __tablename__ = "fixture"
    # rapid_api_id is the match's natural key; app-level dedupe has always kept it
    # unique, so make it a DB invariant (and an index for save_new_fixtures' lookups).
    __table_args__ = (Index("uq_fixture_rapid_api_id", "rapid_api_id", unique=True),)

    status: Mapped[str] = mapped_column(String(5), nullable=False)
    rapid_api_id: Mapped[int] = mapped_column(Integer, nullable=False)
    kick_off: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    venue: Mapped[str | None] = mapped_column(String(255), nullable=True)
    home_team: Mapped[str] = mapped_column(String(255), nullable=False)
    home_team_logo: Mapped[str] = mapped_column(String(255), nullable=False)
    away_team: Mapped[str] = mapped_column(String(255), nullable=False)
    away_team_logo: Mapped[str] = mapped_column(String(255), nullable=False)
    home_odds: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    away_odds: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    draw_odds: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    home_goals: Mapped[int | None] = mapped_column(Integer, nullable=True)
    away_goals: Mapped[int | None] = mapped_column(Integer, nullable=True)
    league_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("league.id"), nullable=True
    )

    league: Mapped["League | None"] = relationship("League")
    bets: Mapped[list["Bet"]] = relationship("Bet", back_populates="fixture")

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
        if self.home_goals < self.away_goals:
            return FixtureResult.AWAY.value
        return FixtureResult.DRAW.value


class Bet(BaseModel):
    __tablename__ = "bet"

    fixture_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("fixture.id"), nullable=False
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("user.id"), nullable=False
    )
    cup_entry_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("cup_entry.id"), nullable=False
    )
    choice: Mapped[str] = mapped_column(String(5), nullable=False)
    stake: Mapped[Decimal] = mapped_column(Numeric(19, 2), nullable=False)
    returns: Mapped[Decimal] = mapped_column(Numeric(19, 2), nullable=False)
    # The decimal odds this bet was struck at, stamped at placement. Internal fact
    # (not on the wire); nullable because pre-existing rows are backfilled by migration.
    odds_struck: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    outcome: Mapped[str] = mapped_column(
        String(10), default=BetOutcome.UNDECIDED.value, nullable=False
    )

    fixture: Mapped["Fixture"] = relationship("Fixture", back_populates="bets")
    user: Mapped["User"] = relationship("User", back_populates="bets")
    cup_entry: Mapped["CupEntry"] = relationship("CupEntry", back_populates="bets")
    ledger_entries: Mapped[list["LedgerEntry"]] = relationship(
        "LedgerEntry", back_populates="bet"
    )

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


class LedgerEntry(BaseModel):
    __tablename__ = "ledger_entry"

    cup_entry_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("cup_entry.id"), nullable=False
    )
    type: Mapped[str] = mapped_column(String(16), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(19, 2), nullable=False)
    balance_after: Mapped[Decimal] = mapped_column(Numeric(19, 2), nullable=False)
    bet_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("bet.id"), nullable=True
    )

    cup_entry: Mapped["CupEntry"] = relationship(
        "CupEntry", back_populates="ledger_entries"
    )
    bet: Mapped["Bet | None"] = relationship("Bet", back_populates="ledger_entries")

    @validates("type")
    def validate_type(self, key: str, value: str) -> str:
        allowed = {e.value for e in LedgerEntryType}
        if value not in allowed:
            raise ValueError(f"Invalid ledger entry type: {value}")
        return value


class Cup(BaseModel):
    __tablename__ = "cup"

    week_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), unique=True, nullable=False
    )
    week_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), default=CupStatus.OPEN.value, nullable=False
    )
    final_entry_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    entries: Mapped[list["CupEntry"]] = relationship("CupEntry", back_populates="cup")

    @validates("status")
    def validate_status(self, key: str, value: str) -> str:
        allowed = {e.value for e in CupStatus}
        if value not in allowed:
            raise ValueError(f"Invalid cup status: {value}")
        return value

    def __str__(self) -> str:
        return f"Cup {self.week_start:%Y-%m-%d} ({self.status})"


class CupEntry(BaseModel):
    __tablename__ = "cup_entry"
    __table_args__ = (UniqueConstraint("cup_id", "user_id", name="uq_cup_entry"),)

    cup_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("cup.id"), nullable=False
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("user.id"), nullable=False
    )
    balance: Mapped[Decimal] = mapped_column(Numeric(19, 2), nullable=False)
    final_rank: Mapped[int | None] = mapped_column(Integer, nullable=True)

    cup: Mapped["Cup"] = relationship("Cup", back_populates="entries")
    user: Mapped["User"] = relationship("User")
    bets: Mapped[list["Bet"]] = relationship("Bet", back_populates="cup_entry")
    ledger_entries: Mapped[list["LedgerEntry"]] = relationship(
        "LedgerEntry", back_populates="cup_entry"
    )

    def debit(self, amount: Decimal) -> None:
        if amount > self.balance:
            raise ValueError("Insufficient cup balance")
        self.balance = self.balance - amount

    def credit(self, amount: Decimal) -> None:
        self.balance = self.balance + amount


class PunditUsage(BaseModel):
    __tablename__ = "pundit_usage"
    __table_args__ = (
        UniqueConstraint("user_id", "day", name="uq_pundit_usage_user_day"),
    )

    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("user.id"), nullable=False
    )
    day: Mapped[date] = mapped_column(Date, nullable=False)
    count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class JobControl(BaseModel):
    __tablename__ = "job_control"

    job_name: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, index=True
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    min_interval_seconds: Mapped[int] = mapped_column(
        Integer, default=300, nullable=False
    )

    last_run_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    def is_due(self) -> bool:
        if not self.enabled:
            return False

        if self.last_run_at is None:
            return True

        return datetime.now(timezone.utc) >= self.last_run_at + timedelta(
            seconds=self.min_interval_seconds
        )

    def __str__(self) -> str:
        return f"{self.job_name} (enabled={self.enabled}, interval={self.min_interval_seconds}s)"


class EventType(str, Enum):
    USER_CREATED = "USER_CREATED"
    CUP_ENTRY_CREATED = "CUP_ENTRY_CREATED"
    BET_PLACED = "BET_PLACED"
    BET_SETTLED = "BET_SETTLED"
    CUP_SETTLED = "CUP_SETTLED"


class Event(BaseModel):
    """Append-only domain event log. Observational only — nothing reads it yet.
    Deliberately has NO foreign key on user_id: events outlive user hard-delete
    (honest gaps), same as frozen cup ranks."""

    __tablename__ = "event"

    # Monotonic total-order key (created_at ties within a transaction). The
    # Identity marker makes the ORM omit seq on insert so Postgres' identity
    # sequence populates it. nullable only so the SQLite test engine — which
    # can't generate a non-PK identity — accepts the omitted value as NULL.
    seq: Mapped[int | None] = mapped_column(
        BigInteger, Identity(always=False), unique=True, nullable=True
    )
    user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(
        JSON, nullable=False, default=dict
    )


def record_event(
    db: Session,
    event_type: EventType,
    user_id: str,
    payload: dict[str, object],
) -> None:
    """Append a domain event in the caller's transaction (no commit of its own).
    Callers emit inside the mutation they describe, so the event and the mutation
    land or roll back together."""
    db.add(Event(type=event_type.value, user_id=user_id, payload=payload))
