"""Dev-only sqladmin auth backend: waves everyone through to `/admin`.

Lets a local stack reach the admin UI without the Cognito Hosted-UI OIDC dance
(which needs a confidential admin client + a localhost callback registered on it).
Selected in `main.py` only when `LOCAL_ADMIN_BYPASS` is set — a flag that lives
solely in `docker-compose.yml`, never in the deployed Terraform env — so prod
always runs the real `AdminAuth`.

Isolation: this module is only imported inside that flag branch, so the running
prod app never pulls it into its import graph.
"""

from sqladmin.authentication import AuthenticationBackend
from starlette.requests import Request


class LocalAdminAuth(AuthenticationBackend):
    async def login(self, request: Request) -> bool:
        return True

    async def logout(self, request: Request) -> bool:
        request.session.clear()
        return True

    async def authenticate(self, request: Request) -> bool:
        return True
