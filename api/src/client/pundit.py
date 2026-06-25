import json
from collections.abc import AsyncGenerator, Callable, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, cast

from openai import AsyncOpenAI, AsyncStream
from openai.types.chat import ChatCompletionChunk
from sqlalchemy.engine import RowMapping

from .pundit_schemas import PunditConversationTurn
from .. import settings
from ..models import Fixture, User
from ..settings import (
    OPENAI_API_KEY,
    OPENAI_BASE_URL,
    OPENAI_MODEL,
    PUNDIT_SYSTEM_PROMPT,
)
from ..utils.logging import logger


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


CompletionStream = Callable[[PunditContext], AsyncGenerator[str, None]]


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def is_email_allowed(email: str | None) -> bool:
    """Whether `email` may use the pundit. Reads the allowlist from settings at
    call time. An empty allowlist disables the gate (allow all)."""
    allowed = {
        _normalize_email(entry)
        for entry in settings.PUNDIT_ALLOWED_EMAILS.split(",")
        if entry.strip()
    }
    if not allowed:
        return True
    return email is not None and _normalize_email(email) in allowed


def _serialize_decimal(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return format(value, ".2f")


def _build_fixture_summaries(fixtures: Sequence[Fixture]) -> list[dict[str, Any]]:
    return [
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
        for fixture in fixtures
    ]


def _build_recent_bet_summaries(
    recent_bets: Sequence[RowMapping],
) -> list[dict[str, Any]]:
    return [
        {
            "bet_id": str(bet["id"]),
            "fixture": f'{bet["home_team"]} vs {bet["away_team"]}',
            "choice": str(bet["choice"]),
            "stake": _serialize_decimal(bet["stake"]),
            "returns": _serialize_decimal(bet["returns"]),
            "outcome": str(bet["outcome"]),
            "kick_off": bet["kick_off"].isoformat(),
            "placed_at": bet["created_at"].isoformat(),
        }
        for bet in recent_bets
    ]


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
        fixtures=_build_fixture_summaries(fixtures),
        recent_bets=_build_recent_bet_summaries(recent_bets),
        conversation=[
            {"role": turn.role, "content": turn.content} for turn in conversation
        ],
    )


def _build_messages(context: PunditContext) -> list[dict[str, str]]:
    preamble = (
        "Here is the data you are grounded in. Only reason about these fixtures and "
        "the user's recent bets.\n\n"
        f"VISIBLE FIXTURES (JSON):\n{json.dumps(context.fixtures)}\n\n"
        f"USER RECENT BETS (JSON):\n{json.dumps(context.recent_bets)}"
    )
    messages: list[dict[str, str]] = [
        {"role": "system", "content": context.system_prompt},
        {"role": "system", "content": preamble},
    ]
    messages.extend(context.conversation)
    return messages


async def openai_completion_stream(
    context: PunditContext,
) -> AsyncGenerator[str, None]:
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is not set")

    # async with on both the client and the stream guarantees the HTTP connection
    # is released whether the consumer finishes, raises, or is cancelled mid-stream
    # (Starlette throws GeneratorExit/CancelledError in here on client disconnect).
    async with AsyncOpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_BASE_URL) as client:
        result = await client.chat.completions.create(
            model=context.model,
            messages=_build_messages(context),  # type: ignore[arg-type]
            stream=True,
        )
        async with cast("AsyncStream[ChatCompletionChunk]", result) as stream:
            async for chunk in stream:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta.content
                if delta:
                    yield delta


async def stream_pundit_response(
    context: PunditContext,
    *,
    completion_stream: CompletionStream = openai_completion_stream,
) -> AsyncGenerator[PunditStreamEvent, None]:
    yield PunditStreamEvent(
        event="message_start",
        data={"role": "assistant", "model": context.model},
    )

    parts: list[str] = []
    inner = completion_stream(context)
    try:
        async for delta in inner:
            parts.append(delta)
            yield PunditStreamEvent(event="message_delta", data={"delta": delta})
    except Exception:
        logger.exception("Pundit completion stream failed mid-stream")
        yield PunditStreamEvent(
            event="error",
            data={"message": "The pundit is unavailable right now. Try again."},
        )
        yield PunditStreamEvent(event="done", data={"finish_reason": "error"})
        return
    finally:
        # On client disconnect Starlette throws GeneratorExit into us here; the
        # async-for above would only close `inner` at GC time, leaving the OpenAI
        # connection open. Close it explicitly so its `async with` unwinds now.
        await inner.aclose()

    full_reply = "".join(parts)
    yield PunditStreamEvent(
        event="message_complete",
        data={"role": "assistant", "content": full_reply},
    )
    yield PunditStreamEvent(event="done", data={"finish_reason": "stop"})
