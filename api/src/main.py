import firebase_admin
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from sqladmin import Admin
from sqladmin.authentication import AuthenticationBackend

from .admin.auth import AdminAuth, oidc_callback
from .admin.admin_views import register_admin_views
from .rapid_api.routes import router as rapid_api_router
from .client.routes import router as client_router
from .database import engine
from .settings import ADMIN_SESSION_SECRET, CORS_ORIGINS, LOCAL_ADMIN_BYPASS

# Init firebase-admin once. No explicit credentials: Application Default
# Credentials on Cloud Run, the Auth emulator env locally; project id from
# GOOGLE_CLOUD_PROJECT.
if not firebase_admin._apps:
    firebase_admin.initialize_app()

app = FastAPI(title="BL API", description="Backend API for BL project", version="0.0.1")
if CORS_ORIGINS is None:
    raise RuntimeError("CORS_ORIGINS must be set")
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
if ADMIN_SESSION_SECRET is None:
    raise RuntimeError("ADMIN_SESSION_SECRET must be set")
app.add_middleware(SessionMiddleware, secret_key=ADMIN_SESSION_SECRET)

app.include_router(rapid_api_router)
app.include_router(client_router)

admin_auth: AuthenticationBackend
if LOCAL_ADMIN_BYPASS:
    from .dev.admin_auth import LocalAdminAuth

    admin_auth = LocalAdminAuth(secret_key=ADMIN_SESSION_SECRET)
else:
    admin_auth = AdminAuth(secret_key=ADMIN_SESSION_SECRET)

admin = Admin(app, engine, title="BL Admin", authentication_backend=admin_auth)
register_admin_views(admin)


app.add_api_route("/auth/callback", oidc_callback, name="oidc_callback")


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}
