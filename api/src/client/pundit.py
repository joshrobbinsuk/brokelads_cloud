import json
import re
from collections.abc import AsyncGenerator, Callable, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, cast

from openai import AsyncOpenAI, AsyncStream
from openai.types.responses import ResponseStreamEvent
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
    username: str | None
    fixtures: list[dict[str, Any]]
    recent_bets: list[dict[str, Any]]
    conversation: list[dict[str, str]]


@dataclass(frozen=True)
class CompletionTextDelta:
    text: str


@dataclass(frozen=True)
class CompletionSearchStarted:
    """The model kicked off a server-side web search."""


@dataclass(frozen=True)
class CompletionSearchFinished:
    """A server-side web search returned; the model is back to composing."""


CompletionChunk = (
    CompletionTextDelta | CompletionSearchStarted | CompletionSearchFinished
)
CompletionStream = Callable[[PunditContext], AsyncGenerator[CompletionChunk, None]]


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def is_unlimited(email: str | None) -> bool:
    """Whether `email` is exempt from the daily pundit cap. Reads the list from
    settings at call time. An empty list means nobody is exempt."""
    unlimited = {
        _normalize_email(entry)
        for entry in settings.PUNDIT_UNLIMITED_EMAILS.split(",")
        if entry.strip()
    }
    return email is not None and _normalize_email(email) in unlimited


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
        username=user.username,
        fixtures=_build_fixture_summaries(fixtures),
        recent_bets=_build_recent_bet_summaries(recent_bets),
        conversation=[
            {"role": turn.role, "content": turn.content} for turn in conversation
        ],
    )


def _build_responses_input(context: PunditContext) -> list[dict[str, str]]:
    preamble = (
        "Here is the slate you are grounded in. Reason about these fixtures and the "
        "user's recent bets.\n\n"
        f"VISIBLE FIXTURES (JSON):\n{json.dumps(context.fixtures)}\n\n"
        f"USER RECENT BETS (JSON):\n{json.dumps(context.recent_bets)}"
    )
    if context.username:
        preamble += (
            f'\n\nThe punter you are talking to goes by "{context.username}" — '
            "address them by name."
        )
    items: list[dict[str, str]] = [{"role": "developer", "content": preamble}]
    items.extend(context.conversation)
    return items


async def openai_completion_stream(
    context: PunditContext,
) -> AsyncGenerator[CompletionChunk, None]:
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is not set")

    # async with on both the client and the stream guarantees the HTTP connection
    # is released whether the consumer finishes, raises, or is cancelled mid-stream
    # (Starlette throws GeneratorExit/CancelledError in here on client disconnect).
    # Responses API + the built-in web_search tool: the model decides when to search,
    # OpenAI runs it server-side, and we stream the answer text deltas plus a
    # marker each time a search starts (the UI says so while it runs).
    async with AsyncOpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_BASE_URL) as client:
        result = await client.responses.create(
            model=context.model,
            instructions=context.system_prompt,
            input=_build_responses_input(context),  # type: ignore[arg-type]
            tools=[{"type": "web_search"}],
            stream=True,
        )
        async with cast("AsyncStream[ResponseStreamEvent]", result) as stream:
            async for event in stream:
                if event.type == "response.output_text.delta":
                    yield CompletionTextDelta(event.delta)
                elif event.type == "response.web_search_call.in_progress":
                    yield CompletionSearchStarted()
                elif event.type == "response.web_search_call.completed":
                    yield CompletionSearchFinished()


_MD_LINK = re.compile(r"\(?\[[^\]]*\]\((?:https?://|www\.)[^)]*\)\)?")
_BARE_URL = re.compile(r"\(?(?:https?://|www\.)[^\s)]+\)?")


def _strip_sources(text: str) -> str:
    """Remove markdown links and bare URLs (web_search citations) from a reply."""
    return _BARE_URL.sub("", _MD_LINK.sub("", text))


class _SourceStripper:
    """Strips source links from a streamed reply, holding back a tail that might be
    an as-yet-incomplete link/URL until it resolves, so nothing leaks mid-stream."""

    def __init__(self) -> None:
        self._buf = ""
        self._emitted = 0

    def feed(self, delta: str) -> str:
        self._buf += delta
        return self._emit(self._safe_len())

    def flush(self) -> str:
        return self._emit(len(self._buf))

    def _emit(self, upto: int) -> str:
        cleaned = _strip_sources(self._buf[:upto])
        out = cleaned[self._emitted :]
        self._emitted = len(cleaned)
        return out

    def _safe_len(self) -> int:
        # Hold back from the start of any construct that could still grow into a link:
        # an unclosed markdown link, or a trailing token that is (or is becoming) a URL.
        buf = self._buf
        holds: list[int] = []
        lb = buf.rfind("[")
        if lb != -1 and not re.search(r"\]\([^)]*\)", buf[lb:]):
            holds.append(lb - 1 if buf[lb - 1 : lb] == "(" else lb)
        trailing = re.search(r"\S+$", buf)
        if trailing:
            low = trailing.group(0).lstrip("(").lower()
            schemes = ("http://", "https://", "www.")
            if low and (
                low.startswith(schemes) or any(s.startswith(low) for s in schemes)
            ):
                holds.append(trailing.start())
        return min(holds) if holds else len(buf)


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
    stripper = _SourceStripper()
    inner = completion_stream(context)
    try:
        async for chunk in inner:
            if isinstance(chunk, CompletionSearchStarted):
                yield PunditStreamEvent(event="status", data={"status": "searching"})
                continue
            if isinstance(chunk, CompletionSearchFinished):
                yield PunditStreamEvent(event="status", data={"status": "thinking"})
                continue
            out = stripper.feed(chunk.text)
            if out:
                parts.append(out)
                yield PunditStreamEvent(event="message_delta", data={"delta": out})
        tail = stripper.flush()
        if tail:
            parts.append(tail)
            yield PunditStreamEvent(event="message_delta", data={"delta": tail})
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
