from fastapi.testclient import TestClient

from src.main import app

client = TestClient(app)


def test_allowed_origin_gets_cors_header() -> None:
    response = client.get("/health", headers={"Origin": "http://localhost:3000"})
    assert (
        response.headers.get("access-control-allow-origin") == "http://localhost:3000"
    )


def test_foreign_origin_does_not_get_cors_header() -> None:
    response = client.get("/health", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in response.headers
