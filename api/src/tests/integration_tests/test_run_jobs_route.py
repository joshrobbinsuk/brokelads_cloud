"""The cron endpoint runs synchronously on the threadpool so a slow upstream
can't block the event loop for every other request, and one run at a time:
a tick that lands mid-run is skipped, not queued behind it. The admin's manual
triggers reach the same jobs through the same lock."""

from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.database import get_db
from src.models import Bet, BetOutcome, FixtureResult, JobControl
from src.rapid_api import routes as routes_module
from src.rapid_api import runner as runner_module
from src.rapid_api.runner import run_job, run_jobs
from src.tests.factories import make_bet, make_fixture, make_user

CRON_KEY = "test-cron-key"


@pytest.fixture()
def cron_client(db: Session, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(routes_module, "CRON_AUTH_KEY", CRON_KEY)
    app = FastAPI()
    app.include_router(routes_module.router)
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app)


def _settleable_bet(db: Session) -> Bet:
    user = make_user(db)
    fixture = make_fixture(db, status="FT", home_goals=2, away_goals=1)
    return make_bet(
        db,
        user=user,
        fixture=fixture,
        choice=FixtureResult.HOME,
        returns=Decimal("35.00"),
    )


def test_runs_due_jobs(
    cron_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[Session] = []

    def record(db: Session) -> bool:
        calls.append(db)
        return True

    monkeypatch.setattr(routes_module, "run_jobs", record)

    response = cron_client.post(
        "/rapid-api/run-jobs", headers={"X-Cron-Auth-Key": CRON_KEY}
    )

    assert response.status_code == 202
    assert response.json()["skipped"] is False
    assert len(calls) == 1
    assert not runner_module._run_lock.locked()


def test_tick_during_a_run_is_skipped(cron_client: TestClient, db: Session) -> None:
    """Exercises the real lock — no patched runner — so this also proves the
    route reports a skip rather than starting a second pass."""
    bet = _settleable_bet(db)
    db.add(JobControl(job_name="settle_bets", enabled=True, min_interval_seconds=0))
    db.commit()

    runner_module._run_lock.acquire()
    try:
        response = cron_client.post(
            "/rapid-api/run-jobs", headers={"X-Cron-Auth-Key": CRON_KEY}
        )
    finally:
        runner_module._run_lock.release()

    assert response.status_code == 202
    assert response.json()["skipped"] is True
    db.refresh(bet)
    assert bet.outcome == BetOutcome.UNDECIDED.value


def test_wrong_key_is_rejected(
    cron_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def must_not_run(db: Session) -> bool:
        raise AssertionError("jobs must not run without the cron key")

    monkeypatch.setattr(routes_module, "run_jobs", must_not_run)

    response = cron_client.post(
        "/rapid-api/run-jobs", headers={"X-Cron-Auth-Key": "wrong"}
    )

    assert response.status_code == 401


def test_admin_trigger_runs_one_job_ignoring_its_clock_gate(db: Session) -> None:
    """No JobControl row at all: the manual trigger is an override, not a tick."""
    bet = _settleable_bet(db)

    assert run_job(db, "settle_bets") is True

    db.refresh(bet)
    assert bet.outcome == BetOutcome.WON.value


def test_admin_trigger_is_refused_while_the_cron_is_running(db: Session) -> None:
    """One lock, both callers — the admin can't start a second settlement pass
    alongside a cron run, which would double-credit a win."""
    bet = _settleable_bet(db)

    runner_module._run_lock.acquire()
    try:
        assert run_job(db, "settle_bets") is False
    finally:
        runner_module._run_lock.release()

    db.refresh(bet)
    assert bet.outcome == BetOutcome.UNDECIDED.value


def test_a_spent_run_budget_defers_the_remaining_jobs(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A run that outlives Cloud Run's 300s keeps the lock while every later
    tick answers "skipped", so ingestion stops silently. Jobs stop starting at
    the budget and the next tick picks them up."""
    bet = _settleable_bet(db)
    db.add(JobControl(job_name="settle_bets", enabled=True, min_interval_seconds=0))
    db.commit()
    monkeypatch.setattr(runner_module, "RUN_BUDGET_SECONDS", 0)

    assert run_jobs(db) is True

    db.refresh(bet)
    assert bet.outcome == BetOutcome.UNDECIDED.value
    assert not runner_module._run_lock.locked()
