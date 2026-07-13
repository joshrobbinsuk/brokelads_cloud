from typing import Any

from firebase_admin import auth
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from ...utils.logging import logger

security = HTTPBearer()


def verify_token(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict[str, Any]:
    token = credentials.credentials
    try:
        # firebase-admin honours FIREBASE_AUTH_EMULATOR_HOST natively: against the
        # emulator it accepts the unsigned local tokens, in the cloud it verifies
        # the real signature. No if-dev branch here.
        claims: dict[str, Any] = auth.verify_id_token(token)
        return claims
    # CertificateFetchError (transient Google outage) deliberately propagates as
    # a 500 — it must not read as "session expired" to the FE.
    except (ValueError, auth.InvalidIdTokenError) as e:
        logger.error(f"Token verification failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token"
        )
