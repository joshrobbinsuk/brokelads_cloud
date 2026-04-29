from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.client.pundit_schemas import AskPunditRequest
from src.client.queries import get_recent_user_bets_for_pundit
from src.client.utils.user import get_current_user
from src.models import Bet, BetOutcome, Fixture, FixtureResult, User, UserStatus
from src.pundit import build_recent_bet_summaries
from src.settings import CLIENT_FIXTURE_LIMIT, OPENAI_MODEL, PUNDIT_RECENT_BET_LIMIT


def create_user(index: int = 1) -> User:
    return User(
        cognito_uuid=f"cognito-{index}",
        email=f"user{index}@example.com",
        status=UserStatus.ACTIVE.value,
        balance=Decimal("100.00"),
    )


def create_fixture(index: int, kick_off: datetime) -> Fixture:
    return Fixture(
        rapid_api_id=index,
        status="NS",
        kick_off=kick_off,
        venue=f"Venue {index}",
        home_team=f"Home {index}",
        home_team_logo=f"https://example.com/home-{index}.png",
        away_team=f"Away {index}",
        away_team_logo=f"https://example.com/away-{index}.png",
        home_odds=Decimal("1.90"),
        away_odds=Decimal("2.80"),
        draw_odds=Decimal("3.10"),
    )


def parse_sse_events(body: str) -> list[tuple[str, dict[str, Any]]]:
    parsed_events: list[tuple[str, dict[str, Any]]] = []
    for raw_event in body.strip().split("\n\n"):
        lines = raw_event.splitlines()
        event_name = lines[0].removeprefix("event: ").strip()
        payload = json.loads(lines[1].removeprefix("data: ").strip())
        parsed_events.append((event_name, payload))
    return parsed_events


def test_ask_pundit_requires_auth(client: TestClient) -> None:
    payload = {
        "fixture_ids": ["fixture-1"],
        "conversation": [{"role": "user", "content": "Who catches your eye?"}],
    }

    response = client.post("/client/pundit", json=payload)

    assert response.status_code == 403


def test_ask_pundit_rejects_fixtures_outside_visible_slate(
    app: FastAPI,
    client: TestClient,
    db: Session,
) -> None:
    user = create_user()
    db.add(user)

    base_kick_off = datetime(2026, 1, 1, tzinfo=timezone.utc)
    fixtures = [
        create_fixture(index=index, kick_off=base_kick_off + timedelta(hours=index))
        for index in range(CLIENT_FIXTURE_LIMIT + 1)
    ]
    db.add_all(fixtures)
    db.commit()

    app.dependency_overrides[get_current_user] = lambda: user

    payload = {
        "fixture_ids": [fixtures[-1].id],
        "conversation": [{"role": "user", "content": "Talk me through the slate"}],
    }

    response = client.post("/client/pundit", json=payload)

    assert response.status_code == 400
    assert fixtures[-1].id in response.json()["detail"]


def test_recent_bet_summaries_are_limited_and_ordered(db: Session) -> None:
    user = create_user()
    fixture = create_fixture(
        index=1,
        kick_off=datetime(2026, 1, 10, 15, 0, tzinfo=timezone.utc),
    )
    db.add_all([user, fixture])
    db.commit()

    base_created_at = datetime(2026, 1, 5, 12, 0, tzinfo=timezone.utc)
    created_bets: list[Bet] = []
    for index in range(PUNDIT_RECENT_BET_LIMIT + 2):
        bet = Bet(
            user_id=user.id,
            fixture_id=fixture.id,
            choice=FixtureResult.HOME.value,
            stake=Decimal("5.00"),
            returns=Decimal("14.50"),
            outcome=BetOutcome.UNDECIDED.value,
            created_at=base_created_at + timedelta(minutes=index),
        )
        created_bets.append(bet)
    db.add_all(created_bets)
    db.commit()

    recent_bets = get_recent_user_bets_for_pundit(db=db, user_id=user.id)
    bet_summaries = build_recent_bet_summaries(recent_bets)

    assert len(bet_summaries) == PUNDIT_RECENT_BET_LIMIT
    assert [summary["bet_id"] for summary in bet_summaries] == [
        created_bets[index].id
        for index in range(len(created_bets) - 1, len(created_bets) - 6, -1)
    ]
    assert bet_summaries[0]["fixture"] == "Home 1 vs Away 1"
    assert bet_summaries[0]["stake"] == "5.00"
    assert bet_summaries[0]["returns"] == "14.50"


def test_ask_pundit_streams_expected_sse_contract(
    app: FastAPI,
    client: TestClient,
    db: Session,
) -> None:
    user = create_user()
    fixture = create_fixture(
        index=1,
        kick_off=datetime(2026, 1, 8, 19, 45, tzinfo=timezone.utc),
    )
    db.add_all([user, fixture])
    db.commit()

    app.dependency_overrides[get_current_user] = lambda: user

    payload = AskPunditRequest(
        fixture_ids=[fixture.id],
        conversation=[
            {"role": "assistant", "content": "Ready when you are."},
            {"role": "user", "content": "Any early thoughts on this one?"},
        ],
    ).model_dump()

    response = client.post("/client/pundit", json=payload)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")

    events = parse_sse_events(response.text)

    event_names = [event_name for event_name, _ in events]

    assert event_names[0] == "message_start"
    assert event_names[-2:] == ["message_complete", "done"]
    assert event_names.count("message_delta") >= 1
    assert events[0][1] == {"role": "assistant", "model": OPENAI_MODEL}
    assert "I won't place bets." in events[-2][1]["content"]
    assert events[-1][1] == {"finish_reason": "stop"}
