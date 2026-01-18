from typing import Any

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from ...database import get_db
from .cognito import verify_token
from ...models import User

from ..queries import (
    get_or_create_user,
)


async def get_current_user(
    db: Session = Depends(get_db),
    token_user: dict[str, Any] = Depends(verify_token),
) -> User:
    cognito_uuid = token_user["sub"]
    email = token_user.get("email")
    if not isinstance(email, str):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing email claim",
        )

    user = get_or_create_user(db, cognito_uuid, email)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get or create user",
        )

    return user
