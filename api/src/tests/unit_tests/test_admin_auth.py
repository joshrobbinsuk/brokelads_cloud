from src.admin.auth import _is_admin
from src.settings import ADMIN_EMAIL


def test_allowed_email_with_verified_email() -> None:
    claims = {"email": ADMIN_EMAIL, "email_verified": True}
    assert _is_admin(claims) is True


def test_allowed_email_without_verified_email() -> None:
    claims = {"email": ADMIN_EMAIL, "email_verified": False}
    assert _is_admin(claims) is False


def test_allowed_email_missing_verified_claim() -> None:
    assert _is_admin({"email": ADMIN_EMAIL}) is False


def test_wrong_email_with_verified_email() -> None:
    claims = {"email": "someone-else@example.com", "email_verified": True}
    assert _is_admin(claims) is False


def test_empty_claims() -> None:
    assert _is_admin({}) is False


def test_email_case_and_whitespace_normalization() -> None:
    claims = {"email": f"  {ADMIN_EMAIL.upper()}  ", "email_verified": True}
    assert _is_admin(claims) is True
