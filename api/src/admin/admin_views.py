from sqladmin import Admin, ModelView
from ..models import (
    League,
    User,
    Fixture,
    Bet,
    TransactionRecord,
    JobControl,
    Cup,
    CupEntry,
)
from .rapid_api_admin import RapidAPIAdmin


class UserAdmin(ModelView, model=User):
    column_list = ["email"]


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


class TransactionRecordAdmin(ModelView, model=TransactionRecord):
    column_list = ["type", "user_balance_before", "user_balance_after", "created_at"]
    column_sortable_list = ["created_at"]


class JobControlAdmin(ModelView, model=JobControl):
    column_list = ["job_name", "last_run_at"]


class CupAdmin(ModelView, model=Cup):
    column_list = ["week_start", "week_end", "status"]
    column_sortable_list = ["week_start"]
    column_searchable_list = ["status"]


class CupEntryAdmin(ModelView, model=CupEntry):
    column_list = ["cup", "user", "balance", "is_winner"]
    column_sortable_list = ["balance"]


def register_admin_views(admin: Admin) -> None:
    admin.add_view(UserAdmin)
    admin.add_view(LeagueAdmin)
    admin.add_view(FixtureAdmin)
    admin.add_view(BetAdmin)
    admin.add_view(TransactionRecordAdmin)
    admin.add_view(JobControlAdmin)
    admin.add_view(CupAdmin)
    admin.add_view(CupEntryAdmin)
    admin.add_view(RapidAPIAdmin)
