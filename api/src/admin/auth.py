from typing import Union

from authlib.integrations.starlette_client import OAuth
from sqladmin.authentication import AuthenticationBackend
from starlette.requests import Request
from starlette.responses import RedirectResponse, Response, PlainTextResponse

from ..settings import ADMIN_EMAIL, GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET


def _normalize_email(v: str | None) -> str | None:
    return v.strip().lower() if v else None


def _is_allowed_email(v: str | None) -> bool:
    return _normalize_email(v) == _normalize_email(ADMIN_EMAIL)


oauth = OAuth()
oauth.register(
    name="google",
    client_id=GOOGLE_CLIENT_ID,
    client_secret=GOOGLE_CLIENT_SECRET,
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile"},
)
google = oauth.create_client("google")


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
            # Start OAuth: send user to Google
            redirect_uri = request.url_for("google_callback")
            return await google.authorize_redirect(request, redirect_uri)

        # Enforce single dev user
        if (
            not _is_allowed_email(user.get("email"))
            or user.get("email_verified") is False
        ):
            request.session.clear()
            return False

        return True


async def google_callback(request: Request) -> Response:
    token = await google.authorize_access_token(request)
    userinfo = token.get("userinfo") or await google.parse_id_token(request, token)

    if not _is_allowed_email(userinfo.get("email")):
        request.session.clear()
        return PlainTextResponse("Not authorized", status_code=403)

    if userinfo.get("email_verified") is False:
        request.session.clear()
        return PlainTextResponse("Email not verified", status_code=403)

    request.session["user"] = userinfo
    return RedirectResponse(request.url_for("admin:index"))
