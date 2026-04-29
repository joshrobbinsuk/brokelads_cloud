from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class PunditConversationTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=2_000)

    @field_validator("content")
    @classmethod
    def strip_content(cls, value: str) -> str:
        stripped_value = value.strip()
        if not stripped_value:
            raise ValueError("Conversation content cannot be empty")
        return stripped_value


class AskPunditRequest(BaseModel):
    fixture_ids: list[str] = Field(min_length=1)
    conversation: list[PunditConversationTurn] = Field(min_length=1, max_length=20)

    @field_validator("fixture_ids")
    @classmethod
    def validate_fixture_ids(cls, value: list[str]) -> list[str]:
        cleaned_fixture_ids: list[str] = []
        for fixture_id in value:
            stripped_fixture_id = fixture_id.strip()
            if not stripped_fixture_id:
                raise ValueError("Fixture IDs cannot be empty")
            cleaned_fixture_ids.append(stripped_fixture_id)
        return cleaned_fixture_ids

    @model_validator(mode="after")
    def validate_last_turn(self) -> "AskPunditRequest":
        if self.conversation[-1].role != "user":
            raise ValueError("Conversation must end with a user turn")
        return self
