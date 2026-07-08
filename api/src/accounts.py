"""Account deletion across the two systems a user lives in: the Cognito pool
and our own database.

Public surface: `delete_user(db, user)`. It removes the Cognito account first
(so the credential is dead before we touch the DB) then cascade-deletes the
user's rows. There is no DB-level ``ON DELETE CASCADE`` — the cascade is spelled
out here so it stays visible and testable, and off the migration.

Cognito needs real AWS credentials (the standard boto3 chain: App Runner's
instance role in the cloud, an access key in the local env). A missing/denied
credential aborts before any DB row is touched. A Cognito account that is simply
absent is not an error: we log a warning, still remove the DB rows, and report
it back so the caller can surface it.
"""

from __future__ import annotations

from typing import Any

import boto3
from sqlalchemy.orm import Session

from .models import Bet, CupEntry, PunditUsage, TransactionRecord, User
from .settings import REGION, USER_POOL_ID
from .utils.logging import logger

_idp_client: Any = None


def _cognito() -> Any:
    global _idp_client
    if _idp_client is None:
        _idp_client = boto3.client("cognito-idp", region_name=REGION)
    return _idp_client


def _delete_cognito_user(cognito_uuid: str) -> bool:
    """Delete the pool account. Returns True if it was there, False if Cognito
    reports no such user (already gone — includes the synthetic seed user, whose
    cognito_uuid never existed in the pool). Any other error propagates."""
    client = _cognito()
    try:
        client.admin_delete_user(UserPoolId=USER_POOL_ID, Username=cognito_uuid)
        return True
    except client.exceptions.UserNotFoundException:
        logger.warning(
            f"No Cognito account for {cognito_uuid} on delete; removing DB rows anyway."
        )
        return False


def _cascade_delete(db: Session, user: User) -> None:
    bet_ids = [b.id for b in db.query(Bet.id).filter(Bet.user_id == user.id)]
    db.query(TransactionRecord).filter(TransactionRecord.bet_id.in_(bet_ids)).delete(
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
    """Hard-delete a user from Cognito and the database. Returns whether a
    Cognito account was actually removed (False = it was already absent)."""
    try:
        cognito_deleted = _delete_cognito_user(user.cognito_uuid)
        _cascade_delete(db, user)
        return cognito_deleted
    except Exception:
        db.rollback()
        logger.exception(f"Error deleting user {user.email}")
        raise
