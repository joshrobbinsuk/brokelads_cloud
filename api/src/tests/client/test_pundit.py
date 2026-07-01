"""Contract tests for POST /client/pundit and the pundit deep module.

The OpenAI call is injected: tests pass a fake `completion_stream` into
`stream_pundit_response`, so the suite needs no API key and hits no network.
"""

from collections.abc import AsyncGenerator
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src import settings
from src.client import routes as routes_module
from src.client.pundit_schemas import PunditConversationTurn
from src.client.queries import (
    fetch_visible_fixture_slate_by_ids,
    get_recent_user_bets_for_pundit,
)
from src.client.utils.user import get_current_user
from src.models import BetOutcome, FixtureResult, User
from src.client.pundit import (
    PunditContext,
    build_pundit_context,
    is_unlimited,
    stream_pundit_response,
)
from src.tests.factories import make_bet, make_fixture, make_league, make_user


def _parse_sse(body: str) -> list[tuple[str, str]]:
    events: list[tuple[str, str]] = []
    for frame in body.split("\n\n"):
        frame = frame.strip()
        if not frame:
            continue
        name = ""
        data = ""
        for line in frame.splitlines():
            if line.startswith("event:"):
                name = line[len("event:") :].strip()
            elif line.startswith("data:"):
                data = line[len("data:") :].strip()
        events.append((name, data))
    return events


def _inject_fake_stream(monkeypatch: pytest.MonkeyPatch, chunks: list[str]) -> None:
    async def fake_completion_stream(
        context: PunditContext,
    ) -> AsyncGenerator[str, None]:
        for chunk in chunks:
            yield chunk

    def patched(context: PunditContext) -> object:
        return stream_pundit_response(context, completion_stream=fake_completion_stream)

    monkeypatch.setattr(routes_module, "stream_pundit_response", patched)


def _override_user(app: FastAPI, user: User) -> None:
    app.dependency_overrides[get_current_user] = lambda: user


@pytest.fixture(autouse=True)
def _pundit_unlimited_default_user(monkeypatch: pytest.MonkeyPatch) -> None:
    # The default test user is exempt from the cap so the streaming/contract
    # tests exercise the stream; the cap is covered in test_pundit_limit.py.
    monkeypatch.setattr(settings, "PUNDIT_UNLIMITED_EMAILS", "user@test.com")


def test_ask_pundit_requires_auth(client: TestClient, db: Session) -> None:
    fixture = make_fixture(db, status="NS")
    resp = client.post(
        "/client/pundit",
        json={
            "fixture_ids": [fixture.id],
            "conversation": [{"role": "user", "content": "Who wins?"}],
        },
    )
    assert resp.status_code == 403


def test_rejects_fixtures_outside_visible_slate(
    client: TestClient, app: FastAPI, db: Session
) -> None:
    user = make_user(db)
    _override_user(app, user)
    finished = make_fixture(db, status="FT", home_goals=1, away_goals=0)

    resp = client.post(
        "/client/pundit",
        json={
            "fixture_ids": [finished.id],
            "conversation": [{"role": "user", "content": "Thoughts?"}],
        },
    )
    assert resp.status_code == 400
    assert finished.id in resp.json()["detail"]


def test_streams_expected_sse_contract(
    client: TestClient,
    app: FastAPI,
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = make_user(db)
    _override_user(app, user)
    fixture = make_fixture(db, status="NS", league_id=make_league(db).id)
    _inject_fake_stream(monkeypatch, ["Hello ", "world"])

    resp = client.post(
        "/client/pundit",
        json={
            "fixture_ids": [fixture.id],
            "conversation": [
                {"role": "user", "content": "Any tips?"},
                {"role": "assistant", "content": "Sure."},
                {"role": "user", "content": "Go on then."},
            ],
        },
    )

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")

    import json

    events = _parse_sse(resp.text)
    names = [name for name, _ in events]

    assert names[0] == "message_start"
    assert json.loads(events[0][1])["model"]

    assert names[-2] == "message_complete"
    assert names[-1] == "done"
    assert json.loads(events[-1][1]) == {"finish_reason": "stop"}

    deltas = [json.loads(d)["delta"] for n, d in events if n == "message_delta"]
    assert len(deltas) >= 1
    complete = json.loads(events[-2][1])["content"]
    assert "".join(deltas) == complete == "Hello world"


def test_recent_bet_summaries_limited_and_ordered(db: Session) -> None:
    user = make_user(db)
    base = datetime.now(timezone.utc)
    for index in range(8):
        fixture = make_fixture(
            db, status="FT", home_goals=1, away_goals=0, kick_off=base
        )
        bet = make_bet(db, user=user, fixture=fixture)
        # Force a deterministic, increasing created_at so newest-first is testable.
        bet.created_at = base + timedelta(minutes=index)
        db.commit()

    rows = get_recent_user_bets_for_pundit(db, user.id)
    assert len(rows) == 5  # PUNDIT_RECENT_BET_LIMIT default

    summaries = build_pundit_context(
        user, [], rows, [PunditConversationTurn(role="user", content="hi")]
    ).recent_bets
    placed = [summary["placed_at"] for summary in summaries]
    assert placed == sorted(placed, reverse=True)


def test_context_serializes_money_as_strings(db: Session) -> None:
    user = make_user(db)
    fixture = make_fixture(
        db,
        status="NS",
        home_odds=Decimal("2.50"),
        draw_odds=Decimal("3.00"),
        away_odds=Decimal("2.75"),
    )
    finished = make_fixture(db, status="FT", home_goals=1, away_goals=0)
    bet = make_bet(
        db,
        user=user,
        fixture=finished,
        stake=Decimal("10.00"),
        returns=Decimal("35.00"),
        outcome=BetOutcome.WON.value,
        choice=FixtureResult.HOME,
    )
    rows = get_recent_user_bets_for_pundit(db, user.id)

    context = build_pundit_context(
        user, [fixture], rows, [PunditConversationTurn(role="user", content="hi")]
    )

    odds = context.fixtures[0]["odds"]
    assert odds == {"home": "2.50", "draw": "3.00", "away": "2.75"}
    assert context.recent_bets[0]["stake"] == "10.00"
    assert context.recent_bets[0]["returns"] == "35.00"
    assert bet.id  # bet persisted


class TestFetchVisibleFixtureSlateByIds:
    def test_preserves_request_order_and_dedupes(self, db: Session) -> None:
        league = make_league(db)
        first = make_fixture(
            db,
            status="NS",
            league_id=league.id,
            kick_off=datetime.now(timezone.utc) + timedelta(days=2),
        )
        second = make_fixture(
            db,
            status="NS",
            league_id=league.id,
            kick_off=datetime.now(timezone.utc) + timedelta(days=1),
        )

        result = fetch_visible_fixture_slate_by_ids(
            db, [second.id, first.id, second.id]
        )
        assert [fixture.id for fixture in result] == [second.id, first.id]

    def test_drops_out_of_slate_ids(self, db: Session) -> None:
        visible = make_fixture(db, status="NS", league_id=make_league(db).id)
        finished = make_fixture(db, status="FT", home_goals=1, away_goals=0)

        result = fetch_visible_fixture_slate_by_ids(
            db, [visible.id, finished.id, "nonexistent"]
        )
        assert [fixture.id for fixture in result] == [visible.id]


class TestIsUnlimited:
    def test_empty_list_exempts_nobody(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings, "PUNDIT_UNLIMITED_EMAILS", "   ,  ")
        assert is_unlimited("anyone@test.com") is False
        assert is_unlimited(None) is False

    def test_normalized_match(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings, "PUNDIT_UNLIMITED_EMAILS", " A@B.com , c@d.com ")
        assert is_unlimited("a@b.com") is True
        assert is_unlimited("A@B.COM ") is True
        assert is_unlimited("e@f.com") is False
        assert is_unlimited(None) is False


def test_mid_stream_error_emits_error_then_done() -> None:
    """When the completion stream raises after message_start, the contract is
    message_start, error, done(error)."""

    async def failing_stream(context: PunditContext) -> AsyncGenerator[str, None]:
        raise RuntimeError("boom")
        yield ""  # type: ignore[unreachable] # only here to mark it a generator

    async def collect() -> list[str]:
        context = PunditContext(
            system_prompt="p",
            model="gpt-5-mini",
            user_id="u1",
            fixtures=[],
            recent_bets=[],
            conversation=[{"role": "user", "content": "hi"}],
        )
        names: list[str] = []
        async for event in stream_pundit_response(
            context, completion_stream=failing_stream
        ):
            names.append(event.event)
        return names

    import asyncio

    names = asyncio.run(collect())
    assert names == ["message_start", "error", "done"]


def test_disconnect_closes_completion_stream() -> None:
    """A consumer that stops early (client disconnect) must promptly close the
    injected completion stream — its cleanup runs synchronously, not at GC."""
    closed = {"value": False}

    async def endless_stream(context: PunditContext) -> AsyncGenerator[str, None]:
        try:
            index = 0
            while True:
                yield f"chunk-{index} "
                index += 1
        finally:
            closed["value"] = True

    async def consume_then_disconnect() -> None:
        context = PunditContext(
            system_prompt="p",
            model="gpt-5-mini",
            user_id="u1",
            fixtures=[],
            recent_bets=[],
            conversation=[{"role": "user", "content": "hi"}],
        )
        events = stream_pundit_response(context, completion_stream=endless_stream)
        seen = 0
        async for _ in events:
            seen += 1
            if seen >= 3:
                break
        await events.aclose()

    import asyncio

    asyncio.run(consume_then_disconnect())
    assert closed["value"] is True


def test_source_links_stripped_from_stream() -> None:
    """web_search citations (markdown links / bare URLs) must never reach the client,
    even when a link is split across streaming chunks."""

    chunks = [
        "Arsenal at (1.95) look ",
        "tasty, son ([fft.com]",
        "(https://www.fourfourtwo.com/x?utm_source=openai)) ",
        "and see https://bbc.co.uk/sport too",
    ]

    async def fake_completion_stream(
        context: PunditContext,
    ) -> AsyncGenerator[str, None]:
        for chunk in chunks:
            yield chunk

    context = PunditContext(
        system_prompt="p",
        model="gpt-5-mini",
        user_id="u1",
        fixtures=[],
        recent_bets=[],
        conversation=[{"role": "user", "content": "hi"}],
    )

    async def collect() -> tuple[str, str]:
        deltas: list[str] = []
        complete = ""
        async for ev in stream_pundit_response(
            context, completion_stream=fake_completion_stream
        ):
            if ev.event == "message_delta":
                deltas.append(str(ev.data["delta"]))
            elif ev.event == "message_complete":
                complete = str(ev.data["content"])
        return "".join(deltas), complete

    import asyncio

    streamed, complete = asyncio.run(collect())
    assert streamed == complete  # delta-concatenation invariant preserved
    for marker in ("http", "](", "www."):
        assert marker not in streamed
    assert "Arsenal at (1.95)" in streamed  # prose and odds survive
    assert "tasty, son" in streamed
