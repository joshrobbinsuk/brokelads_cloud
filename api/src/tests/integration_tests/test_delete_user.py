"""Hard-delete-user, exercised through accounts.delete_user with the Cognito
admin call faked (no AWS in the test env). Covers the cascade, the
already-absent warning path, and the abort-before-DB guarantee."""

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy.orm import Session

from src import accounts
from src.models import (
    Bet,
    CupEntry,
    LedgerEntry,
    LedgerEntryType,
    PunditUsage,
    User,
)
from src.tests.factories import (
    make_bet,
    make_cup,
    make_cup_entry,
    make_fixture,
    make_user,
)


class _UserNotFound(Exception):
    pass


class _FakeCognito:
    def __init__(self, raise_exc: Exception | None = None) -> None:
        self.raise_exc = raise_exc
        self.deleted: list[str] = []
        self.exceptions = SimpleNamespace(UserNotFoundException=_UserNotFound)

    def admin_delete_user(self, UserPoolId: str, Username: str) -> None:
        if self.raise_exc is not None:
            raise self.raise_exc
        self.deleted.append(Username)


def _user_with_history(db: Session) -> User:
    """A user carrying one of every row that FK-references them."""
    user = make_user(db, email="doomed@test.com", cognito_uuid="sub-doomed")
    fixture = make_fixture(db)
    cup = make_cup(db)
    entry = make_cup_entry(db, cup=cup, user=user)
    bet = make_bet(db, user=user, fixture=fixture, cup_entry=entry)
    db.add(
        LedgerEntry(
            cup_entry_id=entry.id,
            bet_id=bet.id,
            type=LedgerEntryType.BET_STAKE.value,
            amount=Decimal("-10.00"),
            balance_after=Decimal("990.00"),
        )
    )
    db.add(PunditUsage(user_id=user.id, day=date(2026, 1, 12), count=3))
    db.commit()
    return user


def _counts(db: Session, user_id: str) -> tuple[int, int, int, int, int]:
    return (
        db.query(User).filter(User.id == user_id).count(),
        db.query(Bet).filter(Bet.user_id == user_id).count(),
        db.query(CupEntry).filter(CupEntry.user_id == user_id).count(),
        db.query(PunditUsage).filter(PunditUsage.user_id == user_id).count(),
        db.query(LedgerEntry).count(),
    )


def test_delete_user_cascades_and_reports_cognito_deleted(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(accounts, "_idp_client", _FakeCognito())
    user = _user_with_history(db)
    user_id = user.id

    cognito_deleted = accounts.delete_user(db, user)

    assert cognito_deleted is True
    assert _counts(db, user_id) == (0, 0, 0, 0, 0)


def test_delete_user_absent_cognito_still_deletes_and_reports_false(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = _FakeCognito(raise_exc=_UserNotFound())
    monkeypatch.setattr(accounts, "_idp_client", fake)
    user = _user_with_history(db)
    user_id = user.id

    cognito_deleted = accounts.delete_user(db, user)

    assert cognito_deleted is False
    assert _counts(db, user_id) == (0, 0, 0, 0, 0)


def test_delete_user_aborts_db_when_cognito_errors(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        accounts, "_idp_client", _FakeCognito(raise_exc=RuntimeError("no creds"))
    )
    user = _user_with_history(db)
    user_id = user.id

    with pytest.raises(RuntimeError):
        accounts.delete_user(db, user)

    # Nothing removed: a credential failure must not orphan-delete the DB rows.
    assert _counts(db, user_id) == (1, 1, 1, 1, 1)
