from sqladmin import BaseView, expose
from starlette.requests import Request

from ..utils.logging import logger
from ..rapid_api.jobs import (
    run_fetch_fixtures,
    run_fetch_odds,
    run_fetch_fixture_updates,
    run_settle_bets,
    run_settle_voided_bets,
)

from ..database import (
    SessionLocal,
)


class RapidAPIAdmin(BaseView):
    name = "RapidAPI"
    icon = "fa-solid fa-futbol"

    @expose("/rapid-api", methods=["GET"])
    async def rapid_api_page(self, request: Request):
        return await self.templates.TemplateResponse(
            request, "rapid-api.html", {"message": "", "success": True}
        )

    @expose("/rapid-api/run/fixtures", methods=["GET"])
    async def run_fixtures(self, request: Request):
        db = SessionLocal()
        try:
            run_fetch_fixtures(db)
            return await self.templates.TemplateResponse(
                request,
                "rapid-api.html",
                {"message": "Fixtures job ran successfully.", "success": True},
            )
        except Exception as e:
            logger.error(f"Fixtures job failed: {e}", exc_info=True)
            return await self.templates.TemplateResponse(
                request,
                "rapid-api.html",
                {"message": f"Fixtures job failed: {e}", "success": False},
            )
        finally:
            db.close()

    @expose("/rapid-api/run/odds", methods=["GET"])
    async def run_odds(self, request: Request):
        db = SessionLocal()
        try:
            run_fetch_odds(db)
            return await self.templates.TemplateResponse(
                request,
                "rapid-api.html",
                {"message": "Odds job ran successfully.", "success": True},
            )
        except Exception as e:
            logger.error(f"Odds job failed: {e}", exc_info=True)
            return await self.templates.TemplateResponse(
                request,
                "rapid-api.html",
                {"message": f"Odds job failed: {e}", "success": False},
            )
        finally:
            db.close()

    @expose("/rapid-api/run/updates", methods=["GET"])
    async def run_updates(self, request: Request):
        db = SessionLocal()
        try:
            run_fetch_fixture_updates(db)
            return await self.templates.TemplateResponse(
                request,
                "rapid-api.html",
                {"message": "Updates job ran successfully.", "success": True},
            )
        except Exception as e:
            logger.error(f"Updates job failed: {e}", exc_info=True)
            return await self.templates.TemplateResponse(
                request,
                "rapid-api.html",
                {"message": f"Updates job failed: {e}", "success": False},
            )
        finally:
            db.close()

    @expose("/rapid-api/run/settle-bets", methods=["GET"])
    async def run_settle_bets_view(self, request: Request):
        db = SessionLocal()
        try:
            run_settle_bets(db)
            return await self.templates.TemplateResponse(
                request,
                "rapid-api.html",
                {
                    "message": "Settle bets job ran successfully.",
                    "success": True,
                },
            )
        except Exception as e:
            logger.error(f"Settle bets job failed: {e}", exc_info=True)
            return await self.templates.TemplateResponse(
                request,
                "rapid-api.html",
                {
                    "message": f"Settle bets job failed: {e}",
                    "success": False,
                },
            )
        finally:
            db.close()

    @expose("/rapid-api/run/settle-voided-bets", methods=["GET"])
    async def run_settle_voided_bets_view(self, request: Request):
        db = SessionLocal()
        try:
            run_settle_voided_bets(db)
            return await self.templates.TemplateResponse(
                request,
                "rapid-api.html",
                {
                    "message": "Settle voided bets job ran successfully.",
                    "success": True,
                },
            )
        except Exception as e:
            logger.error(f"Settle voided bets job failed: {e}", exc_info=True)
            return await self.templates.TemplateResponse(
                request,
                "rapid-api.html",
                {
                    "message": f"Settle voided bets job failed: {e}",
                    "success": False,
                },
            )
        finally:
            db.close()
