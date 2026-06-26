from typing import Optional

from pydantic import BaseModel, Field


class LeagueInfo(BaseModel):
    id: int
    name: str
    type: Optional[str] = None
    logo: Optional[str] = None


class Country(BaseModel):
    name: Optional[str] = None


class League(BaseModel):
    info: LeagueInfo = Field(alias="league")
    country: Country

    def to_db_dict(self) -> dict:
        return {
            "rapid_api_id": self.info.id,
            "name": self.info.name,
            "display_name": self.info.name,
            "type": self.info.type,
            "logo": self.info.logo,
            "country": self.country.name,
        }


class RapidApiLeaguesResponse(BaseModel):
    data: list[League] = Field(alias="response")

    class Config:
        populate_by_name = True
