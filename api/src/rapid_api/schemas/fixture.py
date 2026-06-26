from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field


class Venue(BaseModel):
    name: str | None = None


class StatusModel(BaseModel):
    short: str


class Info(BaseModel):
    id: int
    timestamp: int
    venue: Venue | None = None
    status: StatusModel


class Team(BaseModel):
    name: str
    logo: str


class Teams(BaseModel):
    home: Team
    away: Team


class Goals(BaseModel):
    home: Optional[int]
    away: Optional[int]


### Initial Fixture Fetch ###


class Fixture(BaseModel):
    info: Info = Field(alias="fixture")
    teams: Teams

    def to_db_dict(self) -> dict:
        return {
            "rapid_api_id": self.info.id,
            "kick_off": datetime.fromtimestamp(self.info.timestamp, tz=timezone.utc),
            "status": self.info.status.short,
            "venue": self.info.venue.name if self.info.venue else None,
            "home_team": self.teams.home.name,
            "home_team_logo": self.teams.home.logo,
            "away_team": self.teams.away.name,
            "away_team_logo": self.teams.away.logo,
            "home_odds": None,
            "away_odds": None,
            "draw_odds": None,
            "home_goals": None,
            "away_goals": None,
            "voided": False,
            "voided_message": "",
        }


class RapidApiFixturesResponse(BaseModel):
    data: list[Fixture] = Field(alias="response")

    class Config:
        populate_by_name = True


### Fixture Updates ###


class UpdateFixture(BaseModel):
    info: Info = Field(alias="fixture")
    goals: Goals
    bl_id: Optional[str] = None

    def to_db_dict(self) -> dict:
        return {
            "id": self.bl_id,
            "rapid_api_id": self.info.id,
            "kick_off": datetime.fromtimestamp(self.info.timestamp, tz=timezone.utc),
            "status": self.info.status.short,
            "venue": self.info.venue.name if self.info.venue else None,
            "home_goals": self.goals.home,
            "away_goals": self.goals.away,
        }


class RapidApiUpdateFixturesResponse(BaseModel):
    data: list[UpdateFixture] = Field(alias="response")

    class Config:
        populate_by_name = True
