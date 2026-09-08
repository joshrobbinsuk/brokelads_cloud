"""Sync-first: every client route that touches the database must be a plain
`def` so FastAPI runs it on the threadpool. An `async def` here would put its
psycopg2 calls back on the event loop, where one stall freezes the whole
instance — the shape of the 2026-09-01 outage."""

import inspect

from fastapi.routing import APIRoute

from src.client.routes import router as client_router
from src.client.utils.user import get_current_user

# The pundit route genuinely awaits: it streams an SSE body from AsyncOpenAI.
# Its DB prelude lives in a `def` dependency instead.
STREAMING_ROUTES = {"ask_pundit"}


def test_database_routes_run_on_the_threadpool() -> None:
    coroutine_routes = {
        route.endpoint.__name__
        for route in client_router.routes
        if isinstance(route, APIRoute) and inspect.iscoroutinefunction(route.endpoint)
    }
    assert coroutine_routes == STREAMING_ROUTES


def test_get_current_user_runs_on_the_threadpool() -> None:
    assert not inspect.iscoroutinefunction(get_current_user)
