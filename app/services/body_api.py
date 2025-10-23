import os
import mimetypes
import httpx
from typing import Dict
from ..config import settings


class BodyApiClient:
    def __init__(self) -> None:
        self.base = settings.body_api_base.rstrip("/")
        self.username = settings.body_api_username
        self.password = settings.body_api_password
        self._token: str | None = None

    async def _ensure_token(self) -> str:
        if self._token:
            return self._token
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{self.base}/auth/login",
                data={"username": self.username, "password": self.password},
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            resp.raise_for_status()
            data = resp.json()
            token = data.get("access_token")
            if not token:
                raise RuntimeError("Body API login failed: no access_token")
            self._token = token
            return token

    async def analyze_file(self, height_cm: float, image_path: str) -> Dict[str, float]:
        token = await self._ensure_token()
        with open(image_path, "rb") as f:
            guessed, _ = mimetypes.guess_type(image_path)
            content_type = guessed or "image/jpeg"
            files = {"image": (os.path.basename(image_path), f, content_type)}
            data = {"height": str(height_cm)}
            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.post(
                    f"{self.base}/measurements/analyze",
                    headers={"Authorization": f"Bearer {token}"},
                    files=files,
                    data=data,
                )
                resp.raise_for_status()
                payload = resp.json()
                if not payload.get("success"):
                    raise RuntimeError("Body API analyze failed")
                measurements = payload.get("measurements") or {}
                return {k: float(v) for k, v in measurements.items() if isinstance(v, (int, float, str))}

