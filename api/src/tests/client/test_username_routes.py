"""Contract tests for PUT /client/me/username: happy path (including renames),
plus the 409 (taken) and 422 (bad format) mappings the frontend relies on."""

from typing import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.client.routes import router as client_router
from src.client.utils.cognito import verify_token
from src.database import get_db
from src.models import User
from src.tests.factories import make_user


@pytest.fixture()
def user(db: Session) -> User:
    return make_user(db, email="me@test.com", cognito_uuid="me")


@pytest.fixture()
def client(db: Session, user: User) -> Iterator[TestClient]:
    app = FastAPI()
    app.include_router(client_router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[verify_token] = lambda: {
        "sub": user.cognito_uuid,
        "email": user.email,
    }
    with TestClient(app) as test_client:
        yield test_client


def test_sets_username(client: TestClient) -> None:
    resp = client.put("/client/me/username", json={"username": "josh_r"})
    assert resp.status_code == 200
    assert resp.json()["username"] == "josh_r"
    assert client.get("/client/me").json()["username"] == "josh_r"


def test_taken_returns_409(client: TestClient, db: Session) -> None:
    make_user(db, email="other@test.com", cognito_uuid="other", username="josh_r")

    resp = client.put("/client/me/username", json={"username": "JOSH_R"})

    assert resp.status_code == 409


def test_bad_format_returns_422(client: TestClient) -> None:
    resp = client.put("/client/me/username", json={"username": "no spaces"})
    assert resp.status_code == 422


def test_rename_succeeds(client: TestClient) -> None:
    client.put("/client/me/username", json={"username": "first"})

    resp = client.put("/client/me/username", json={"username": "second"})

    assert resp.status_code == 200
    assert resp.json()["username"] == "second"
    assert client.get("/client/me").json()["username"] == "second"


def test_rename_to_taken_returns_409(client: TestClient, db: Session) -> None:
    make_user(db, email="other@test.com", cognito_uuid="other", username="taken")
    client.put("/client/me/username", json={"username": "first"})

    resp = client.put("/client/me/username", json={"username": "taken"})

    assert resp.status_code == 409


def test_rename_own_casing_succeeds(client: TestClient) -> None:
    client.put("/client/me/username", json={"username": "josh_r"})

    resp = client.put("/client/me/username", json={"username": "JOSH_R"})

    assert resp.status_code == 200
    assert resp.json()["username"] == "JOSH_R"
