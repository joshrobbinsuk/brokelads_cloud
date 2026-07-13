"""Account deletion across the two systems a user lives in: the Identity
Platform (Firebase Auth) account and our own database.

Public surface: `delete_user(db, user)`. It removes the auth account first
(so the credential is dead before we touch the DB) then cascade-deletes the
user's rows. There is no DB-level ``ON DELETE CASCADE`` — the cascade is spelled
out here so it stays visible and testable, and off the migration.

Firebase Auth needs Identity Platform admin on the runtime identity (ADC on
Cloud Run, the emulator locally). A missing/denied credential aborts before any
DB row is touched. An auth account that is simply absent is not an error: we log
a warning, still remove the DB rows, and report it back so the caller can
surface it.
"""

from __future__ import annotations

from firebase_admin import auth
from sqlalchemy.orm import Session

from .models import Bet, CupEntry, LedgerEntry, PunditUsage, User
from .utils.logging import logger


def _delete_auth_user(auth_uid: str) -> bool:
    """Delete the Firebase Auth account. Returns True if it was there, False if
    Firebase reports no such user (already gone — includes the synthetic seed
    user, whose auth_uid never existed in Firebase). Any other error propagates."""
    try:
        auth.delete_user(auth_uid)
        return True
    except auth.UserNotFoundError:
        logger.warning(
            f"No auth account for {auth_uid} on delete; removing DB rows anyway."
        )
        return False


def _cascade_delete(db: Session, user: User) -> None:
    entry_ids = [
        e.id for e in db.query(CupEntry.id).filter(CupEntry.user_id == user.id)
    ]
    db.query(LedgerEntry).filter(LedgerEntry.cup_entry_id.in_(entry_ids)).delete(
        synchronize_session=False
    )
    db.query(Bet).filter(Bet.user_id == user.id).delete(synchronize_session=False)
    db.query(CupEntry).filter(CupEntry.user_id == user.id).delete(
        synchronize_session=False
    )
    db.query(PunditUsage).filter(PunditUsage.user_id == user.id).delete(
        synchronize_session=False
    )
    db.delete(user)
    db.commit()


def delete_user(db: Session, user: User) -> bool:
    """Hard-delete a user from Firebase Auth and the database. Returns whether an
    auth account was actually removed (False = it was already absent)."""
    try:
        auth_deleted = _delete_auth_user(user.auth_uid)
        _cascade_delete(db, user)
        return auth_deleted
    except Exception:
        db.rollback()
        logger.exception(f"Error deleting user {user.email}")
        raise
