from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy.engine import RowMapping

from .client.pundit_schemas import PunditConversationTurn
from .models import Fixture, User
from .settings import OPENAI_MODEL, PUNDIT_SYSTEM_PROMPT


@dataclass(frozen=True)
class PunditStreamEvent:
    event: str
    data: dict[str, Any]


@dataclass(frozen=True)
class PunditContext:
    system_prompt: str
    model: str
    user_id: str
    fixtures: list[dict[str, Any]]
    recent_bets: list[dict[str, Any]]
    conversation: list[dict[str, str]]


def _serialize_decimal(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return format(value, ".2f")


def build_fixture_summaries(fixtures: Sequence[Fixture]) -> list[dict[str, Any]]:
    fixture_summaries: list[dict[str, Any]] = []
    for fixture in fixtures:
        fixture_summaries.append(
            {
                "fixture_id": fixture.id,
                "home_team": fixture.home_team,
                "away_team": fixture.away_team,
                "venue": fixture.venue,
                "kick_off": fixture.kick_off.isoformat(),
                "odds": {
                    "home": _serialize_decimal(fixture.home_odds),
                    "draw": _serialize_decimal(fixture.draw_odds),
                    "away": _serialize_decimal(fixture.away_odds),
                },
            }
        )
    return fixture_summaries


def build_recent_bet_summaries(
    recent_bets: Sequence[RowMapping],
) -> list[dict[str, str]]:
    bet_summaries: list[dict[str, str]] = []
    for bet in recent_bets:
        bet_summaries.append(
            {
                "bet_id": str(bet["id"]),
                "fixture_id": str(bet["fixture_id"]),
                "fixture": f'{bet["home_team"]} vs {bet["away_team"]}',
                "choice": str(bet["choice"]),
                "stake": _serialize_decimal(bet["stake"]) or "0.00",
                "returns": _serialize_decimal(bet["returns"]) or "0.00",
                "outcome": str(bet["outcome"]),
                "kick_off": bet["kick_off"].isoformat(),
                "placed_at": bet["created_at"].isoformat(),
            }
        )
    return bet_summaries


def build_pundit_context(
    user: User,
    fixtures: Sequence[Fixture],
    recent_bets: Sequence[RowMapping],
    conversation: Sequence[PunditConversationTurn],
) -> PunditContext:
    return PunditContext(
        system_prompt=PUNDIT_SYSTEM_PROMPT,
        model=OPENAI_MODEL,
        user_id=user.id,
        fixtures=build_fixture_summaries(fixtures),
        recent_bets=build_recent_bet_summaries(recent_bets),
        conversation=[
            {"role": turn.role, "content": turn.content} for turn in conversation
        ],
    )


def _chunk_text(content: str, chunk_size: int = 48) -> list[str]:
    return [
        content[index : index + chunk_size]
        for index in range(0, len(content), chunk_size)
    ]


def _build_placeholder_reply(context: PunditContext) -> str:
    fixture_count = len(context.fixtures)
    recent_bet_count = len(context.recent_bets)
    return (
        f"I've got {fixture_count} fixtures on the slate and {recent_bet_count} "
        "of your recent bets in the notebook. Ask about the visible matches and "
        "I'll give you a short steer, not a sure thing, and I won't place bets."
    )


async def stream_pundit_response(
    context: PunditContext,
) -> AsyncIterator[PunditStreamEvent]:
    reply = _build_placeholder_reply(context)
    yield PunditStreamEvent(
        event="message_start",
        data={"role": "assistant", "model": context.model},
    )
    for chunk in _chunk_text(reply):
        yield PunditStreamEvent(
            event="message_delta",
            data={"delta": chunk},
        )
    yield PunditStreamEvent(
        event="message_complete",
        data={"role": "assistant", "content": reply},
    )
    yield PunditStreamEvent(
        event="done",
        data={"finish_reason": "stop"},
    )
