"""Contract tests for PUT /client/me/shirt: happy path, 422 for a slug outside
the fixed sets, and that it's reflected on GET /client/me."""

from typing import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.client.routes import router as client_router
from src.client.utils.firebase import verify_token
from src.database import get_db
from src.models import User
from src.tests.factories import make_user

RED_SHIRT = {
    "background": "teal",
    "body": "red",
    "pattern": "stripes",
    "pattern_colour": "white",
    "motif": "fox",
}
BLUE_SHIRT = {
    "background": "gold",
    "body": "blue",
    "pattern": "hoops",
    "pattern_colour": "white",
    "motif": None,
}


@pytest.fixture()
def user(db: Session) -> User:
    return make_user(db, email="me@test.com", auth_uid="me")


@pytest.fixture()
def client(db: Session, user: User) -> Iterator[TestClient]:
    app = FastAPI()
    app.include_router(client_router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[verify_token] = lambda: {
        "sub": user.auth_uid,
        "email": user.email,
    }
    with TestClient(app) as test_client:
        yield test_client


def test_sets_shirt(client: TestClient) -> None:
    resp = client.put("/client/me/shirt", json=RED_SHIRT)
    assert resp.status_code == 200
    assert resp.json()["shirt"] == RED_SHIRT
    assert client.get("/client/me").json()["shirt"] == RED_SHIRT


def test_null_motif_is_accepted(client: TestClient) -> None:
    resp = client.put("/client/me/shirt", json=BLUE_SHIRT)
    assert resp.status_code == 200
    assert resp.json()["shirt"]["motif"] is None


def test_invalid_slug_returns_422(client: TestClient) -> None:
    resp = client.put("/client/me/shirt", json={**RED_SHIRT, "body": "black"})
    assert resp.status_code == 422


def test_change_shirt_succeeds(client: TestClient) -> None:
    client.put("/client/me/shirt", json=RED_SHIRT)

    resp = client.put("/client/me/shirt", json=BLUE_SHIRT)

    assert resp.status_code == 200
    assert resp.json()["shirt"] == BLUE_SHIRT
