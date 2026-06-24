from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from sqladmin import Admin

from .admin.auth import AdminAuth, oidc_callback
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


app.add_api_route("/auth/callback", oidc_callback, name="oidc_callback")


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}
