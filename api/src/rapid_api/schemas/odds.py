from pydantic import BaseModel, Field
from typing import Optional


class OddsValue(BaseModel):
    value: str  # "Home", "Draw", "Away"
    odd: str  # "2.55"


class Bet(BaseModel):
    id: int
    name: str
    values: list[OddsValue]

    def is_match_winner(self) -> bool:
        return self.name == "Match Winner"

    def has_complete_odds(self) -> bool:
        values = {v.value for v in self.values}
        return {"Home", "Draw", "Away"}.issubset(values)

    def get_odds_dict(self) -> dict[str, float]:
        return {v.value: float(v.odd) for v in self.values}


class Bookmaker(BaseModel):
    id: int
    name: str
    bets: list[Bet]

    def get_match_winner_bet(self) -> Optional[Bet]:
        for bet in self.bets:
            if bet.is_match_winner() and bet.has_complete_odds():
                return bet
        return None


class OddsFixture(BaseModel):
    id: int


class Odds(BaseModel):
    fixture: OddsFixture
    bookmakers: list[Bookmaker]
    bl_id: Optional[str] = None

    def first_complete_odds(self) -> Optional[dict[str, float]]:
        for bookmaker in self.bookmakers:
            bet = bookmaker.get_match_winner_bet()
            if bet:
                return bet.get_odds_dict()
        return None

    def to_db_dict(self) -> Optional[dict[str, object]]:
        odds = self.first_complete_odds()
        if not odds:
            return None

        return {
            "id": self.bl_id,
            "rapid_api_id": self.fixture.id,
            "home_odds": odds["Home"],
            "draw_odds": odds["Draw"],
            "away_odds": odds["Away"],
        }


class RapidApiOddsResponse(BaseModel):
    data: list[Odds] = Field(alias="response")

    class Config:
        populate_by_name = True

    def first_complete_odds(self) -> Optional[Odds]:
        for odds_response in self.data:
            if odds_response.first_complete_odds():
                return odds_response
        return None
