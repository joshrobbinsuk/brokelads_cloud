from typing import Any

import requests
from functools import lru_cache

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError

from ...utils.logging import logger
from ...settings import REGION, USER_POOL_ID, COGNITO_CLIENT_ID

security = HTTPBearer()

ISSUER = f"https://cognito-idp.{REGION}.amazonaws.com/{USER_POOL_ID}"
JWKS_URL = f"{ISSUER}/.well-known/jwks.json"


@lru_cache()
def get_jwks() -> dict[str, Any]:
    return requests.get(JWKS_URL).json()


def verify_token(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict[str, Any]:
    token = credentials.credentials
    jwks = get_jwks()

    try:
        claims = jwt.decode(
            token,
            jwks,
            algorithms=["RS256"],
            audience=COGNITO_CLIENT_ID,
            issuer=ISSUER,
            options={"verify_exp": True},
        )
        return claims
    except JWTError as e:
        logger.error(f"Token verification failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token"
        )
