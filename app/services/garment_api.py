import os
import httpx
from typing import Dict, Any
from ..config import settings


class GarmentApiClient:
    def __init__(self) -> None:
        self.base = settings.garments_api_base.rstrip("/")
        self._token: str | None = None

    async def _ensure_token(self) -> str:
        if self._token:
            return self._token
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(f"{self.base}/auth/token")
            resp.raise_for_status()
            data = resp.json()
            token = data.get("token")
            if not token:
                raise RuntimeError("Garment API token issuance failed")
            self._token = token
            return token

    async def process_image(self, image_path: str, category_id: int, true_size: str, unit: str) -> Dict[str, Any]:
        token = await self._ensure_token()
        with open(image_path, "rb") as f:
            files = {"image": (os.path.basename(image_path), f, "application/octet-stream")}
            data = {
                "category_id": str(category_id),
                "true_size": true_size,
                "unit": unit,
            }
            async with httpx.AsyncClient(timeout=None) as client:
                resp = await client.post(
                    f"{self.base}/process",
                    headers={"Authorization": f"Bearer {token}"},
                    files=files,
                    data=data,
                )
                resp.raise_for_status()
                return resp.json()
