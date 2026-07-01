from collections.abc import AsyncGenerator
from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src import settings
from src.client import routes as routes_module
from src.client.pundit import PunditContext, stream_pundit_response
from src.client.queries import increment_pundit_usage, pundit_count_today
from src.client.utils.user import get_current_user
from src.models import PunditUsage, User
from src.tests.factories import make_fixture, make_league, make_user
from src.utils.weeks import london_today


@pytest.fixture(autouse=True)
def _nobody_unlimited(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "PUNDIT_UNLIMITED_EMAILS", "")
    monkeypatch.setattr(settings, "PUNDIT_DAILY_LIMIT", 10)


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


def _ask(client: TestClient, fixture_id: str) -> int:
    resp = client.post(
        "/client/pundit",
        json={
            "fixture_ids": [fixture_id],
            "conversation": [{"role": "user", "content": "Any tips?"}],
        },
    )
    return resp.status_code


def test_under_limit_serves_and_increments(
    client: TestClient,
    app: FastAPI,
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = make_user(db)
    _override_user(app, user)
    fixture = make_fixture(db, status="NS", league_id=make_league(db).id)
    _inject_fake_stream(monkeypatch, ["Hi"])
    today = london_today(datetime.now(timezone.utc))

    assert _ask(client, fixture.id) == 200
    assert pundit_count_today(db, user, today) == 1


def test_at_limit_returns_429(
    client: TestClient,
    app: FastAPI,
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = make_user(db)
    _override_user(app, user)
    fixture = make_fixture(db, status="NS", league_id=make_league(db).id)
    _inject_fake_stream(monkeypatch, ["Hi"])
    today = london_today(datetime.now(timezone.utc))
    for _ in range(settings.PUNDIT_DAILY_LIMIT):
        increment_pundit_usage(db, user, today)

    resp = client.post(
        "/client/pundit",
        json={
            "fixture_ids": [fixture.id],
            "conversation": [{"role": "user", "content": "Any tips?"}],
        },
    )

    assert resp.status_code == 429
    assert resp.json()["detail"] == (
        "You've used all 10 of today's pundit questions. Try again tomorrow."
    )
    # The blocked request must not have consumed another slot.
    assert pundit_count_today(db, user, today) == settings.PUNDIT_DAILY_LIMIT


def test_unlimited_email_bypasses_cap_without_writing_a_row(
    client: TestClient,
    app: FastAPI,
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "PUNDIT_UNLIMITED_EMAILS", "vip@test.com")
    user = make_user(db, email="vip@test.com", cognito_uuid="vip")
    _override_user(app, user)
    fixture = make_fixture(db, status="NS", league_id=make_league(db).id)
    _inject_fake_stream(monkeypatch, ["Hi"])

    assert _ask(client, fixture.id) == 200
    assert db.query(PunditUsage).count() == 0


def test_increment_rolls_over_across_london_days(db: Session) -> None:
    user = make_user(db)
    monday = london_today(datetime(2026, 3, 30, 12, 0, tzinfo=timezone.utc))
    tuesday = london_today(datetime(2026, 3, 31, 12, 0, tzinfo=timezone.utc))
    assert monday != tuesday

    for _ in range(3):
        increment_pundit_usage(db, user, monday)
    increment_pundit_usage(db, user, tuesday)

    assert pundit_count_today(db, user, monday) == 3
    assert pundit_count_today(db, user, tuesday) == 1
