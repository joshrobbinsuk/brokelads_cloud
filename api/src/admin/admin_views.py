from fastapi import HTTPException
from fastapi.concurrency import run_in_threadpool
from sqladmin import Admin, ModelView
from starlette.requests import Request

from .. import accounts
from ..database import SessionLocal
from ..models import (
    League,
    User,
    Fixture,
    Bet,
    LedgerEntry,
    JobControl,
    Cup,
    CupEntry,
)
from .rapid_api_admin import RapidAPIAdmin


def _hard_delete_user(pk: str) -> tuple[str, bool]:
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == pk).first()
        if user is None:
            raise HTTPException(status_code=404)
        return user.email, accounts.delete_user(db, user)
    finally:
        db.close()


class UserAdmin(ModelView, model=User):
    column_list = ["email", "username", "status", "created_at"]
    can_delete = True

    async def delete_model(self, request: Request, pk: str) -> None:
        """Route the standard delete button through the two-system hard delete
        (Firebase Auth + DB cascade) rather than SQLAdmin's bare ORM delete,
        which would FK-violate on any user who has placed a bet. An auth account
        that was already absent isn't fatal — the DB rows still go, but we raise
        so the admin sees the warning (SQLAdmin alerts the raised detail).

        Stays `async def` and hops explicitly: SQLAdmin calls a sync view inline
        on the event loop, and the delete is a Firebase REST call (120s timeout)
        plus a five-table cascade — minutes of frozen instance on a bad day."""
        email, auth_deleted = await run_in_threadpool(_hard_delete_user, pk)
        if not auth_deleted:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Removed {email} from the database, but no matching auth "
                    "account existed — it was already absent. Refresh to confirm."
                ),
            )


class LeagueAdmin(ModelView, model=League):
    column_list = ["name", "country", "type", "active"]
    column_searchable_list = ["name", "country"]
    column_sortable_list = ["name", "country", "type", "active"]
    can_edit = True


class FixtureAdmin(ModelView, model=Fixture):
    column_list = ["home_team", "away_team", "league", "status", "kick_off"]
    column_sortable_list = ["kick_off"]
    column_searchable_list = ["league.name", "home_team", "away_team", "status"]


class BetAdmin(ModelView, model=Bet):
    column_list = ["user", "fixture", "choice", "stake", "created_at"]
    column_sortable_list = ["created_at"]


class LedgerEntryAdmin(ModelView, model=LedgerEntry):
    column_list = ["cup_entry", "type", "amount", "balance_after", "bet", "created_at"]
    column_sortable_list = ["created_at"]


class JobControlAdmin(ModelView, model=JobControl):
    column_list = ["job_name", "last_run_at"]


class CupAdmin(ModelView, model=Cup):
    column_list = ["week_start", "week_end", "status"]
    column_sortable_list = ["week_start"]
    column_searchable_list = ["status"]


class CupEntryAdmin(ModelView, model=CupEntry):
    column_list = ["cup", "user", "balance", "final_rank"]
    column_sortable_list = ["balance"]


def register_admin_views(admin: Admin) -> None:
    admin.add_view(UserAdmin)
    admin.add_view(LeagueAdmin)
    admin.add_view(FixtureAdmin)
    admin.add_view(BetAdmin)
    admin.add_view(LedgerEntryAdmin)
    admin.add_view(JobControlAdmin)
    admin.add_view(CupAdmin)
    admin.add_view(CupEntryAdmin)
    admin.add_view(RapidAPIAdmin)
