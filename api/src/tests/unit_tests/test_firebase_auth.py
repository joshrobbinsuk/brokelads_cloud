"""verify_token dependency: maps firebase-admin's verify_id_token result to a
claims dict, and its invalid/expired errors to a 401 — no network (verify_id_token
is monkeypatched)."""

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from firebase_admin import auth

from src.client.utils import firebase


def _creds(token: str = "tok") -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


def test_valid_token_returns_claims(monkeypatch: pytest.MonkeyPatch) -> None:
    claims = {"sub": "uid-123", "email": "a@test.com"}
    monkeypatch.setattr(firebase.auth, "verify_id_token", lambda token: claims)

    assert firebase.verify_token(_creds()) == claims


def test_invalid_token_raises_401(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(token: str) -> dict[str, object]:
        raise auth.InvalidIdTokenError("bad token")

    monkeypatch.setattr(firebase.auth, "verify_id_token", _boom)

    with pytest.raises(HTTPException) as exc:
        firebase.verify_token(_creds())
    assert exc.value.status_code == 401
    assert exc.value.detail == "Invalid token"


def test_malformed_token_value_error_raises_401(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _boom(token: str) -> dict[str, object]:
        raise ValueError("empty token")

    monkeypatch.setattr(firebase.auth, "verify_id_token", _boom)

    with pytest.raises(HTTPException) as exc:
        firebase.verify_token(_creds(""))
    assert exc.value.status_code == 401
