"""API-Football's Pro plan allows 5 requests/second, and the odds job loops over
up to 50 fixtures on a warm connection. Without pacing it outruns that whenever
the API answers quickly, and the rejections arrive as HTTP 200 with an errors
body — so odds were silently dropped while the daily quota sat untouched."""

from typing import Any

import pytest

from src.rapid_api import external_calls


class _Response:
    status_code = 200
    text = "{}"

    @staticmethod
    def json() -> dict[str, Any]:
        return {"errors": [], "response": []}


@pytest.fixture()
def paced(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """A fake clock that only moves when something sleeps, so the assertions are
    about the pacing rather than about how fast the machine ran the test."""
    clock = {"now": 1000.0}
    slept: list[float] = []

    def fake_sleep(seconds: float) -> None:
        slept.append(seconds)
        clock["now"] += seconds

    monkeypatch.setattr(external_calls.time, "monotonic", lambda: clock["now"])
    monkeypatch.setattr(external_calls.time, "sleep", fake_sleep)
    monkeypatch.setattr(external_calls.http_session, "get", lambda *a, **k: _Response())
    monkeypatch.setattr(external_calls, "_last_request_at", 0.0)
    return slept


def test_the_first_call_does_not_wait(paced: list[float]) -> None:
    external_calls.fetch_odds_by_fixture(fixture_id=1)

    assert paced == []


def test_back_to_back_calls_are_paced_apart(paced: list[float]) -> None:
    for fixture_id in range(4):
        external_calls.fetch_odds_by_fixture(fixture_id=fixture_id)

    # Three waits for four calls, each the full interval — 4 requests/second.
    assert paced == pytest.approx([external_calls._MIN_INTERVAL_SECONDS] * 3)


def test_a_call_after_a_long_gap_does_not_wait(
    paced: list[float], monkeypatch: pytest.MonkeyPatch
) -> None:
    external_calls.fetch_odds_by_fixture(fixture_id=1)
    monkeypatch.setattr(external_calls, "_last_request_at", 0.0)

    external_calls.fetch_odds_by_fixture(fixture_id=2)

    assert paced == []
