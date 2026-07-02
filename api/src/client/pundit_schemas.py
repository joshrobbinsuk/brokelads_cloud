from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class PunditConversationTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=2000)

    @field_validator("content")
    @classmethod
    def strip_and_reject_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("content must not be blank")
        return stripped


class AskPunditRequest(BaseModel):
    fixture_ids: list[str] = Field(min_length=1)
    conversation: list[PunditConversationTurn] = Field(min_length=1, max_length=200)

    @field_validator("fixture_ids")
    @classmethod
    def strip_and_reject_blank_ids(cls, value: list[str]) -> list[str]:
        cleaned = [fixture_id.strip() for fixture_id in value]
        if any(not fixture_id for fixture_id in cleaned):
            raise ValueError("fixture_ids must not contain blank ids")
        return cleaned

    @model_validator(mode="after")
    def last_turn_must_be_user(self) -> "AskPunditRequest":
        if self.conversation[-1].role != "user":
            raise ValueError("conversation must end with a user turn")
        return self
