from typing import Any, Union

from authlib.integrations.starlette_client import OAuth
from sqladmin.authentication import AuthenticationBackend
from starlette.requests import Request
from starlette.responses import RedirectResponse, Response, PlainTextResponse

from ..settings import (
    ADMIN_EMAIL,
    ADMIN_GOOGLE_CLIENT_ID,
    ADMIN_GOOGLE_CLIENT_SECRET,
)
from ..utils.logging import logger


def _normalize_email(v: str | None) -> str | None:
    return v.strip().lower() if v else None


def _is_allowed_email(v: str | None) -> bool:
    return _normalize_email(v) == _normalize_email(ADMIN_EMAIL)


def _is_admin(claims: dict[str, Any]) -> bool:
    if not _is_allowed_email(claims.get("email")):
        return False
    return claims.get("email_verified") is True


oauth = OAuth()
oauth.register(
    name="oidc",
    client_id=ADMIN_GOOGLE_CLIENT_ID,
    client_secret=ADMIN_GOOGLE_CLIENT_SECRET,
    server_metadata_url=(
        "https://accounts.google.com/.well-known/openid-configuration"
    ),
    client_kwargs={"scope": "openid email profile"},
)
oidc = oauth.create_client("oidc")


class AdminAuth(AuthenticationBackend):
    async def login(self, request: Request) -> bool:
        # not used in OAuth flow
        return True

    async def logout(self, request: Request) -> bool:
        request.session.clear()
        return True

    async def authenticate(self, request: Request) -> Union[bool, Response]:
        user = request.session.get("user")
        if not user:
            redirect_uri = request.url_for("oidc_callback")
            return await oidc.authorize_redirect(request, redirect_uri)

        if not _is_admin(user):
            request.session.clear()
            return False

        return True


async def oidc_callback(request: Request) -> Response:
    try:
        token = await oidc.authorize_access_token(request)
        # Authlib validates the id_token and populates `userinfo` from its claims on the OIDC
        # code flow. Google's id_token carries the `email` + `email_verified` claims the admin
        # gate checks. No fallback: a missing userinfo is an error, not a reason to source claims
        # from somewhere lacking those claims.
        claims = token.get("userinfo")
        if not claims:
            raise RuntimeError("OIDC token did not include id_token claims (userinfo)")

        if not _is_admin(claims):
            request.session.clear()
            return PlainTextResponse("Not authorized", status_code=403)

        request.session["user"] = dict(claims)
        return RedirectResponse(request.url_for("admin:index"))
    except Exception:
        logger.exception("oidc_callback failed")
        raise
