"""Username: freely renameable, case-insensitive uniqueness (excluding the
caller's own row), and its appearance on the cup leaderboard alongside
lifetime wins."""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.client.cup import leaderboard
from src.client.queries import (
    UsernameTakenError,
    set_username,
)
from src.client.schemas import SetUsernameRequest
from src.tests.factories import (
    make_cup,
    make_cup_entry,
    make_user,
)


class TestSetUsername:
    def test_sets_username_on_first_call(self, db: Session) -> None:
        user = make_user(db)

        updated = set_username(db, user, "josh_r")

        assert updated.username == "josh_r"

    def test_rename_succeeds(self, db: Session) -> None:
        user = make_user(db)
        set_username(db, user, "josh_r")

        updated = set_username(db, user, "someone_else")

        assert updated.username == "someone_else"

    def test_own_casing_change_succeeds(self, db: Session) -> None:
        user = make_user(db)
        set_username(db, user, "josh_r")

        updated = set_username(db, user, "JOSH_R")

        assert updated.username == "JOSH_R"

    def test_rename_to_taken_rejects(self, db: Session) -> None:
        user = make_user(db)
        set_username(db, user, "josh_r")
        other = make_user(db, email="other@test.com", auth_uid="c-other")
        set_username(db, other, "taken")

        with pytest.raises(UsernameTakenError):
            set_username(db, user, "taken")

    def test_rejects_duplicate_case_insensitively(self, db: Session) -> None:
        first = make_user(db, email="a@test.com", auth_uid="c-a")
        set_username(db, first, "JoshR")
        second = make_user(db, email="b@test.com", auth_uid="c-b")

        with pytest.raises(UsernameTakenError):
            set_username(db, second, "joshr")

    def test_preserves_entered_case(self, db: Session) -> None:
        user = make_user(db)

        updated = set_username(db, user, "JoshR")

        assert updated.username == "JoshR"

    def test_db_rejects_case_variant_even_bypassing_set_username(
        self, db: Session
    ) -> None:
        # The functional unique index on lower(username) is the invariant, not
        # just the app-layer check in set_username.
        make_user(db, email="a@test.com", auth_uid="c-a", username="JoshR")

        with pytest.raises(IntegrityError):
            make_user(db, email="b@test.com", auth_uid="c-b", username="joshr")


class TestSetUsernameRequestValidation:
    @pytest.mark.parametrize("bad", ["ab", "a" * 21, "has space", "dot.dot", ""])
    def test_rejects_bad_format(self, bad: str) -> None:
        with pytest.raises(ValidationError):
            SetUsernameRequest(username=bad)

    @pytest.mark.parametrize("ok", ["abc", "Josh_R", "a" * 20, "user123"])
    def test_accepts_valid(self, ok: str) -> None:
        assert SetUsernameRequest(username=ok).username == ok


class TestLeaderboardUsername:
    def test_row_carries_username_and_lifetime_wins(self, db: Session) -> None:
        cup = make_cup(db)
        winner = make_user(db, email="w@test.com", auth_uid="c-w")
        set_username(db, winner, "champ")
        # A prior settled cup this user won, plus their entry in the current cup.
        past = make_cup(
            db,
            week_start=datetime(2026, 1, 5, 0, 0, tzinfo=timezone.utc),
            status="SETTLED",
        )
        make_cup_entry(db, cup=past, user=winner, final_rank=1)
        make_cup_entry(db, cup=cup, user=winner)

        rows = leaderboard(db, cup)

        assert len(rows) == 1
        assert rows[0]["username"] == "champ"
        assert rows[0]["cups_won"] == 1

    def test_cups_won_defaults_to_zero(self, db: Session) -> None:
        cup = make_cup(db)
        user = make_user(db)
        set_username(db, user, "rookie")
        make_cup_entry(db, cup=cup, user=user)

        rows = leaderboard(db, cup)

        assert rows[0]["cups_won"] == 0
