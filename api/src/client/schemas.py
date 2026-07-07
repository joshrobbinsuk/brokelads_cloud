from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator
from ..models import FixtureResult
from ..settings import AVATAR_IDS


class CreateBetRequest(BaseModel):
    fixture_id: str
    choice: FixtureResult
    stake: Decimal = Field(gt=0, decimal_places=2)


class SetUsernameRequest(BaseModel):
    username: str = Field(min_length=3, max_length=20, pattern=r"^[A-Za-z0-9_]+$")


class SetAvatarRequest(BaseModel):
    avatar: str

    @field_validator("avatar")
    @classmethod
    def validate_avatar(cls, value: str) -> str:
        if value not in AVATAR_IDS:
            raise ValueError(f"Unknown avatar id: {value}")
        return value


class LeagueOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    display_name: str
    logo: str | None = None


class FixtureResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    status: str
    rapid_api_id: int
    kick_off: datetime
    venue: str | None
    home_team: str
    home_team_logo: str
    away_team: str
    away_team_logo: str
    home_odds: Decimal | None
    away_odds: Decimal | None
    draw_odds: Decimal | None
    home_goals: int | None
    away_goals: int | None
    created_at: datetime
    updated_at: datetime | None
    league: LeagueOut | None = None

    @field_serializer("home_odds", "away_odds", "draw_odds")
    def serialize_odds(self, value: Decimal | None) -> str | None:
        return str(value) if value is not None else None


class CupSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    week_start: datetime
    week_end: datetime
    status: str
