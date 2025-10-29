import os
import tempfile
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, File, UploadFile, HTTPException, Body, Form, Request

from ..security import verify_api_key
from ..services.vto_providers import get_provider
from ..services.vto_providers.nanobanana import NanoBananaProvider
from ..config import settings


router = APIRouter(prefix="/try-on", tags=["try-on"], dependencies=[Depends(verify_api_key)])

# In-memory task store for nano provider (dev/POC). Replace with persistent store in production.
_nano_tasks: Dict[str, Dict[str, Any]] = {}


@router.post("")
async def try_on(
    user_image: UploadFile = File(...),
    garment_image: UploadFile = File(...),
    callback_url: Optional[str] = Form(None),
):
    """Unified try-on endpoint.
    - If VTO_PROVIDER=mock (default): returns an immediate side-by-side composite served at /files/....
    - If VTO_PROVIDER=nano: uploads files to this server and returns a public URL pair + creates a NanoBanana task.
      Requires PUBLIC_BASE_URL and NANO_API_KEY. Response is 202 with task payload.
    """
    provider_name = (settings.vto_provider or "mock").lower()

    # Save incoming files to storage
    os.makedirs(settings.storage_dir, exist_ok=True)
    with tempfile.NamedTemporaryFile(delete=False, dir=settings.storage_dir, suffix=os.path.splitext(user_image.filename or "user.jpg")[1] or ".jpg") as utmp:
        utmp.write(await user_image.read())
        user_path = utmp.name
    with tempfile.NamedTemporaryFile(delete=False, dir=settings.storage_dir, suffix=os.path.splitext(garment_image.filename or "garment.jpg")[1] or ".jpg") as gtmp:
        gtmp.write(await garment_image.read())
        garment_path = gtmp.name

    if provider_name == "nano":
        # Need PUBLIC_BASE_URL to build public URLs Nano can fetch
        if not settings.public_base_url:
            raise HTTPException(status_code=400, detail="PUBLIC_BASE_URL not configured for nano provider")
        rel_user = os.path.basename(user_path)
        rel_garment = os.path.basename(garment_path)
        public_user = f"{settings.public_base_url.rstrip('/')}/files/{rel_user}"
        public_garment = f"{settings.public_base_url.rstrip('/')}/files/{rel_garment}"
        if not settings.nano_api_key:
            raise HTTPException(status_code=400, detail="NANO_API_KEY not configured")
        provider = NanoBananaProvider()
        # Use our public callback if none provided
        cb = callback_url or f"{settings.public_base_url.rstrip('/')}/v1/try-on/nano/callback"
        payload = await provider.create_task(
            prompt="Generate a try-on image",
            image_urls=[public_user, public_garment],
            callback_url=cb,
            output_format="png",
            image_size="1:1",
        )
        # Normalize task id
        task_id = payload.get("id") or payload.get("taskId") or payload.get("job_id") or payload.get("data", {}).get("id")
        if task_id:
            _nano_tasks[task_id] = {"status": "queued", "provider": "nano", "payload": payload}
        # Return 202 to indicate async processing
        return {"success": True, "provider": "nano", "status": "queued", "task_id": task_id, "task": payload}

    # default: mock provider composite
    provider = get_provider(provider_name)
    try:
        out_path = await provider.generate(user_path, garment_path)
    finally:
        # keep inputs in storage for observability; they are small and auto-rotated operationally
        pass

    if not out_path or not os.path.exists(out_path):
        raise HTTPException(status_code=500, detail="Try-on provider failed to generate an image")

    rel_name = os.path.basename(out_path)
    url = f"/files/{rel_name}"
    return {"success": True, "provider": provider_name, "result_image_url": url}


class NanoCreateTaskBody(BaseException):
    pass


@router.post("/nanobanana/create-task")
async def nano_create_task(
    model: Optional[str] = Body(None),
    prompt: str = Body(...),
    image_urls: List[str] = Body(..., embed=True),
    output_format: Optional[str] = Body(None),
    image_size: Optional[str] = Body(None),
    callBackUrl: Optional[str] = Body(None),
):
    if not settings.nano_api_key:
        raise HTTPException(status_code=400, detail="NANO_API_KEY not configured")

    provider = NanoBananaProvider()
    payload = await provider.create_task(
        prompt=prompt,
        image_urls=image_urls,
        callback_url=callBackUrl,
        output_format=output_format,
        image_size=image_size,
    )
    return payload


@router.post("/nano/callback")
async def nano_callback(request: Request, body: Dict[str, Any] = Body(...)):
    # Store raw callback. Try to extract status and output URL(s).
    task_id = body.get("id") or body.get("taskId") or body.get("job_id") or body.get("data", {}).get("id")
    status = body.get("status") or body.get("state") or body.get("data", {}).get("status")
    result_urls: List[str] = []
    data = body.get("data") or {}
    # Common patterns
    if isinstance(body.get("output"), dict) and isinstance(body["output"].get("image_urls"), list):
        result_urls = body["output"]["image_urls"]
    elif isinstance(data.get("output"), dict) and isinstance(data["output"].get("image_urls"), list):
        result_urls = data["output"]["image_urls"]
    elif isinstance(body.get("image_urls"), list):
        result_urls = body["image_urls"]

    entry = _nano_tasks.get(task_id, {"provider": "nano"})
    entry.update({"status": status or entry.get("status") or "processing", "callback": body})
    if result_urls:
        entry["result_image_url"] = result_urls[0]
    _nano_tasks[task_id] = entry
    return {"ok": True}


@router.get("/status")
async def get_status(task_id: str):
    entry = _nano_tasks.get(task_id)
    if not entry:
        raise HTTPException(status_code=404, detail="task not found")
    out: Dict[str, Any] = {
        "task_id": task_id,
        "status": entry.get("status", "processing"),
        "provider": entry.get("provider", "nano"),
    }
    url = entry.get("result_image_url")
    if url:
        # Ensure absolute URL
        out["result_image_url"] = url if url.startswith("http") else f"{settings.public_base_url.rstrip('/')}{url}"
    return out
