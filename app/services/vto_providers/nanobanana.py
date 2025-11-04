import json
from typing import List
import httpx
from ...config import settings
from .base import TryOnProvider


class NanoBananaProvider:
    async def generate(self, user_image_path: str, garment_image_path: str) -> str:
        # In production, you'd upload images to a CDN and pass URLs.
        # Here, we error if API key is missing.
        if not settings.nano_api_key:
            raise RuntimeError("NANO_API_KEY not configured")

        # TODO: In a real flow, upload user & garment images to storage to get URLs
        # Placeholder: raise to indicate missing URLs
        raise RuntimeError("nanobanana requires image URLs; supply via extended API or upload pipeline")

    @staticmethod
    async def create_task(prompt: str, image_urls: List[str], callback_url: str | None = None, output_format: str | None = None, image_size: str | None = None) -> dict:
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {settings.nano_api_key}",
        }
        payload = {
            "model": settings.nano_model,
            "input": {
                "prompt": prompt,
                "image_urls": image_urls,
            },
        }
        if callback_url:
            payload["callBackUrl"] = callback_url
        if output_format:
            payload["input"]["output_format"] = output_format
        if image_size:
            payload["input"]["image_size"] = image_size

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(f"{settings.nano_api_base}/api/v1/jobs/createTask", headers=headers, json=payload)
            resp.raise_for_status()
            return resp.json()

    @staticmethod
    async def query_task(task_id: str) -> dict:
        """Query task status directly from NanoBanana. Returns the raw JSON.
        Docs: GET /api/v1/jobs/recordInfo?taskId=...
        """
        headers = {
            "Authorization": f"Bearer {settings.nano_api_key}",
        }
        params = {"taskId": task_id}
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(f"{settings.nano_api_base}/api/v1/jobs/recordInfo", headers=headers, params=params)
            
            # Check HTTP status first
            if resp.status_code != 200:
                # Try to parse error response
                try:
                    error_data = resp.json()
                    return error_data
                except:
                    resp.raise_for_status()
            
            data = resp.json()
            
            # Check for error codes in response body
            code = data.get("code")
            is_error_code = False
            if code:
                if isinstance(code, int) and code != 200:
                    is_error_code = True
                elif isinstance(code, str) and str(code).lower() not in ("success", "ok", "200"):
                    is_error_code = True
            
            if is_error_code:
                # Return the error response as-is so caller can handle it
                return data
            
            return data

