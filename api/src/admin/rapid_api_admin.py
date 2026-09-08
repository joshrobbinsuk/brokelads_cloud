from fastapi.concurrency import run_in_threadpool
from sqladmin import BaseView, expose
from starlette.requests import Request
from starlette.responses import Response

from ..utils.logging import logger
from ..rapid_api.runner import run_job

from ..database import (
    SessionLocal,
)


def _run_job_with_session(job_name: str) -> bool:
    """Session lifecycle inside the threadpooled call, not around it. A job that
    finds nothing to do leaves an uncommitted read open, and Session.close()
    then issues a ROLLBACK — a network round trip to Neon that would otherwise
    land on the event loop, which is the exact thing this file is avoiding."""
    db = SessionLocal()
    try:
        return run_job(db, job_name)
    finally:
        db.close()


class RapidAPIAdmin(BaseView):
    name = "RapidAPI"
    icon = "fa-solid fa-futbol"

    async def _run(self, request: Request, job_name: str, label: str) -> Response:
        """Run one job from the admin and render the outcome.

        These views stay `async def` and hop explicitly: SQLAdmin's `@expose`
        registers them wrapped in an async `login_required` that calls a sync
        view inline on the event loop (sqladmin/authentication.py:69), so
        declaring them `def` would not move them off it. A job is up to 45s of
        outbound calls; on the loop that freezes every other request on the
        instance, /health included. `run_job` takes the same lock as the cron,
        so a click during a tick is refused rather than run alongside it.
        """
        try:
            if await run_in_threadpool(_run_job_with_session, job_name):
                message, success = f"{label} job ran successfully.", True
            else:
                message, success = (
                    f"{label} job not started: a run is already in progress.",
                    False,
                )
        except Exception as e:
            logger.error(f"{label} job failed: {e}", exc_info=True)
            message, success = f"{label} job failed: {e}", False
        return await self.templates.TemplateResponse(
            request, "rapid-api.html", {"message": message, "success": success}
        )

    @expose("/rapid-api", methods=["GET"])
    async def rapid_api_page(self, request: Request) -> Response:
        return await self.templates.TemplateResponse(
            request, "rapid-api.html", {"message": "", "success": True}
        )

    @expose("/rapid-api/run/leagues", methods=["GET"])
    async def run_leagues(self, request: Request) -> Response:
        return await self._run(request, "fetch_leagues", "Leagues")

    @expose("/rapid-api/run/fixtures", methods=["GET"])
    async def run_fixtures(self, request: Request) -> Response:
        return await self._run(request, "fetch_fixtures", "Fixtures")

    @expose("/rapid-api/run/odds", methods=["GET"])
    async def run_odds(self, request: Request) -> Response:
        return await self._run(request, "fetch_odds", "Odds")

    @expose("/rapid-api/run/updates", methods=["GET"])
    async def run_updates(self, request: Request) -> Response:
        return await self._run(request, "fetch_fixture_updates", "Updates")

    @expose("/rapid-api/run/settle-bets", methods=["GET"])
    async def run_settle_bets_view(self, request: Request) -> Response:
        return await self._run(request, "settle_bets", "Settle bets")

    @expose("/rapid-api/run/settle-voided-bets", methods=["GET"])
    async def run_settle_voided_bets_view(self, request: Request) -> Response:
        return await self._run(request, "settle_voided_bets", "Settle voided bets")

    @expose("/rapid-api/run/close-cups", methods=["GET"])
    async def run_close_cups_view(self, request: Request) -> Response:
        return await self._run(request, "close_cups", "Close cups")
