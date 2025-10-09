import pytest
from fastapi.testclient import TestClient
from app.main import app


client = TestClient(app)


def test_health():
    r = client.get("/v1/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_token():
    r = client.post("/v1/auth/token")
    assert r.status_code == 200
    assert "token" in r.json()
