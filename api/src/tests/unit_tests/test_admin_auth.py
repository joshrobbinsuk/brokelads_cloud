from src.admin.auth import _is_admin
from src.settings import ADMIN_EMAIL


def test_allowed_email_with_admins_group() -> None:
    claims = {"email": ADMIN_EMAIL, "cognito:groups": ["admins"]}
    assert _is_admin(claims) is True


def test_allowed_email_without_admins_group() -> None:
    claims = {"email": ADMIN_EMAIL, "cognito:groups": ["users"]}
    assert _is_admin(claims) is False


def test_allowed_email_missing_groups_claim() -> None:
    assert _is_admin({"email": ADMIN_EMAIL}) is False


def test_wrong_email_with_admins_group() -> None:
    claims = {"email": "someone-else@example.com", "cognito:groups": ["admins"]}
    assert _is_admin(claims) is False


def test_empty_claims() -> None:
    assert _is_admin({}) is False


def test_email_case_and_whitespace_normalization() -> None:
    claims = {"email": f"  {ADMIN_EMAIL.upper()}  ", "cognito:groups": ["admins"]}
    assert _is_admin(claims) is True
