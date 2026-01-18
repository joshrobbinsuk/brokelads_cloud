from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import RedirectResponse, PlainTextResponse, Response
from starlette.requests import Request

from sqladmin import Admin

from .admin.auth import AdminAuth, oauth, _is_allowed_email  # adjust imports as needed
from .admin.admin_views import register_admin_views
from .rapid_api.routes import router as rapid_api_router
from .client.routes import router as client_router
from .database import engine
from .settings import ADMIN_SESSION_SECRET

app = FastAPI(title="BL API", description="Backend API for BL project", version="0.0.1")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
if ADMIN_SESSION_SECRET is None:
    raise RuntimeError("ADMIN_SESSION_SECRET must be set")
app.add_middleware(SessionMiddleware, secret_key=ADMIN_SESSION_SECRET)

app.include_router(rapid_api_router)
app.include_router(client_router)

admin = Admin(
    app,
    engine,
    title="BL Admin",
    authentication_backend=AdminAuth(secret_key=ADMIN_SESSION_SECRET),
)
register_admin_views(admin)


@app.get("/auth/google", name="google_callback")
async def google_callback(request: Request) -> Response:
    token = await oauth.google.authorize_access_token(request)
    userinfo = token.get("userinfo") or await oauth.google.parse_id_token(
        request, token
    )

    if not _is_allowed_email(userinfo.get("email")):
        request.session.clear()
        return PlainTextResponse("Not authorized", status_code=403)

    if userinfo.get("email_verified") is False:
        request.session.clear()
        return PlainTextResponse("Email not verified", status_code=403)

    request.session["user"] = userinfo
    return RedirectResponse(request.url_for("admin:index"))


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}
