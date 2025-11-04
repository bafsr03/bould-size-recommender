import os
import json
import pytest
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


@pytest.mark.parametrize("provider_name", ["nano", "nanobanana", "nano-banana"])
@respx.mock
def test_callback_no_auth_and_status_flow(monkeypatch, tmp_path, provider_name):
    # Configure nano provider and public base URL
    monkeypatch.setenv("NANO_API_KEY", "test-key")
    monkeypatch.setenv("VTO_PROVIDER", provider_name)
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://example.com")
    settings.nano_api_key = "test-key"
    settings.vto_provider = provider_name
    settings.public_base_url = "https://example.com"

    # Mock createTask
    create_task_route = respx.post(f"{settings.nano_api_base}/api/v1/jobs/createTask").mock(
        return_value=httpx.Response(200, json={"code": 200, "message": "success", "data": {"taskId": "task_abc"}})
    )

    # Prepare two dummy files
    user_file = tmp_path / "user.jpg"
    garment_file = tmp_path / "garment.jpg"
    user_file.write_bytes(b"user-bytes")
    garment_file.write_bytes(b"garment-bytes")

    with open(user_file, "rb") as uf, open(garment_file, "rb") as gf:
        r = client.post(
            "/v1/try-on",
            files={
                "user_image": ("user.jpg", uf, "image/jpeg"),
                "garment_image": ("garment.jpg", gf, "image/jpeg"),
            },
            data={},
            headers={"x-api-key": settings.api_key},
        )
    assert r.status_code == 200
    data = r.json()
    assert data["provider"] == "nano"
    assert data["status"] == "queued"
    task_id = data["task_id"]
    assert task_id == "task_abc"
    assert create_task_route.called

    # Simulate NanoBanana callback (no API key provided)
    cb_payload = {
        "id": task_id,
        "status": "success",
        "output": {"image_urls": ["https://cdn.example.com/out.png"]},
    }
    cb = client.post("/v1/try-on/nano/callback", json=cb_payload)
    assert cb.status_code == 200, cb.text
    assert cb.json()["ok"] is True

    # Now status should include result_image_url (requires api key)
    st = client.get(f"/v1/try-on/status?task_id={task_id}", headers={"x-api-key": settings.api_key})
    assert st.status_code == 200
    stj = st.json()
    assert stj["status"] in ("success", "completed")
    assert stj["result_image_url"] == "https://cdn.example.com/out.png"
