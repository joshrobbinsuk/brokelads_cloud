from decimal import Decimal
from pydantic import BaseModel, Field
from ..models import FixtureResult


class CreateBetRequest(BaseModel):
    fixture_id: str
    choice: FixtureResult
    stake: Decimal = Field(gt=0, decimal_places=2)
