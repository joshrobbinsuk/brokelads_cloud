"""Contract tests for PUT /client/me/avatar: happy path, 422 for an id outside
the fixed set, and that it's reflected on GET /client/me."""

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


def test_sets_avatar(client: TestClient) -> None:
    resp = client.put("/client/me/avatar", json={"avatar": "fox-red"})
    assert resp.status_code == 200
    assert resp.json()["avatar"] == "fox-red"
    assert client.get("/client/me").json()["avatar"] == "fox-red"


def test_invalid_id_returns_422(client: TestClient) -> None:
    resp = client.put("/client/me/avatar", json={"avatar": "dragon-black"})
    assert resp.status_code == 422


def test_change_avatar_succeeds(client: TestClient) -> None:
    client.put("/client/me/avatar", json={"avatar": "fox-red"})

    resp = client.put("/client/me/avatar", json={"avatar": "goat-teal"})

    assert resp.status_code == 200
    assert resp.json()["avatar"] == "goat-teal"
