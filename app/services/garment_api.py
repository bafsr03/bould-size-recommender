import os
import mimetypes
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
            guessed, _ = mimetypes.guess_type(image_path)
            content_type = guessed or "image/jpeg"
            files = {"image": (os.path.basename(image_path), f, content_type)}
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

    async def read_json_file(self, absolute_path: str) -> Dict[str, Any]:
        """Fetch a JSON file produced by the garments API using its /files endpoint.
        This avoids trying to read container-local paths from the orchestrator container.
        """
        token = await self._ensure_token()
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.get(
                f"{self.base}/files",
                params={"path": absolute_path},
                headers={"Authorization": f"Bearer {token}"},
            )
            resp.raise_for_status()
            # Response is the raw file contents; parse as JSON
            return resp.json()

