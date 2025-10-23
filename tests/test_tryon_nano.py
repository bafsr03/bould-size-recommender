import os
import json
import respx
import httpx
from fastapi.testclient import TestClient
from app.main import app
from app.config import settings


client = TestClient(app)


@respx.mock
def test_nano_create_task_ok(monkeypatch):
    monkeypatch.setenv("NANO_API_KEY", "test-key")
    # Re-load settings if needed
    settings.nano_api_key = "test-key"

    route = respx.post(f"{settings.nano_api_base}/api/v1/jobs/createTask").mock(
        return_value=httpx.Response(200, json={"code": 200, "message": "success", "data": {"taskId": "task_123"}})
    )

    payload = {
        "prompt": "test",
        "image_urls": ["https://example.com/a.jpg"],
        "output_format": "png",
        "image_size": "1:1",
        "callBackUrl": "https://your-domain.com/api/callback",
    }
    r = client.post("/v1/try-on/nanobanana/create-task", json=payload, headers={"x-api-key": settings.api_key})
    assert r.status_code == 200
    data = r.json()
    assert data["code"] == 200
    assert data["data"]["taskId"] == "task_123"
    assert route.called

