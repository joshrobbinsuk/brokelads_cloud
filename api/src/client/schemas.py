from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel, ConfigDict, Field, field_serializer
from ..models import FixtureResult


class CreateBetRequest(BaseModel):
    fixture_id: str
    choice: FixtureResult
    stake: Decimal = Field(gt=0, decimal_places=2)


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
