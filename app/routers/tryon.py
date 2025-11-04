import os
import tempfile
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, File, UploadFile, HTTPException, Body, Form, Request

from ..security import verify_api_key
from ..services.vto_providers import get_provider
from ..services.vto_providers.nanobanana import NanoBananaProvider
from ..config import settings


router = APIRouter(prefix="/try-on", tags=["try-on"], dependencies=[Depends(verify_api_key)])
# Public router without auth dependencies (for third-party callbacks)
public_router = APIRouter(prefix="/try-on", tags=["try-on"]) 

# In-memory task store for nano provider (dev/POC). Replace with persistent store in production.
_nano_tasks: Dict[str, Dict[str, Any]] = {}


def _safe_suffix(filename: Optional[str], fallback: str = ".jpg") -> str:
    """Return a filesystem-safe suffix derived from the uploaded filename."""
    if not filename:
        return fallback
    name = os.path.basename(filename)
    # Strip query strings or fragments that may be appended (common with CDN URLs)
    name = name.split("?")[0].split("#")[0]
    suffix = os.path.splitext(name)[1]
    return suffix or fallback


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
    is_nano_provider = provider_name in {"nano", "nanobanana", "nano-banana", "nano-banana-edit"}

    # Save incoming files to storage
    os.makedirs(settings.storage_dir, exist_ok=True)
    with tempfile.NamedTemporaryFile(delete=False, dir=settings.storage_dir, suffix=_safe_suffix(user_image.filename, ".jpg")) as utmp:
        utmp.write(await user_image.read())
        user_path = utmp.name
    with tempfile.NamedTemporaryFile(delete=False, dir=settings.storage_dir, suffix=_safe_suffix(garment_image.filename, ".jpg")) as gtmp:
        gtmp.write(await garment_image.read())
        garment_path = gtmp.name

    if is_nano_provider:
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
        data_block = payload.get("data", {}) if isinstance(payload.get("data"), dict) else {}
        task_id = (
            payload.get("id")
            or payload.get("taskId")
            or payload.get("job_id")
            or payload.get("jobId")
            or data_block.get("id")
            or data_block.get("taskId")
            or data_block.get("task_id")
            or data_block.get("jobId")
            or data_block.get("job_id")
        )
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


@public_router.post("/nano/callback")
async def nano_callback(request: Request, body: Dict[str, Any] = Body(...)):
    # Store raw callback. Try to extract status and output URL(s).
    task_id = body.get("id") or body.get("taskId") or body.get("job_id") or body.get("jobId") or body.get("data", {}).get("id") or body.get("data", {}).get("taskId")
    data = body.get("data") or {}
    
    # Log callback for debugging
    import structlog
    logger = structlog.get_logger("bould")
    
    if not task_id:
        logger.warning("nano_callback_missing_task_id", body_keys=list(body.keys()), data_keys=list(data.keys()) if isinstance(data, dict) else None)
        # Try to extract from raw body string if available
        return {"ok": True, "warning": "task_id not found in callback"}
    
    # Extract status from multiple possible locations
    status = (
        body.get("status") 
        or body.get("state") 
        or data.get("status") 
        or data.get("state")
        or body.get("code")  # Some APIs use code field
    )
    
    # Normalize status values
    status_str = str(status).lower() if status else None
    if status_str in ("fail", "failed", "error", "failure"):
        status = "fail"
    elif status_str in ("success", "completed", "done", "finish"):
        status = "success"
    elif status_str in ("pending", "processing", "generating", "running"):
        status = "processing"
    else:
        status = status or "processing"
    
    result_urls: List[str] = []
    fail_msg = (
        body.get("failMsg")
        or body.get("failMessage")
        or body.get("message")  # Generic message field
        or body.get("msg")
        or data.get("failMsg")
        or data.get("failMessage")
        or data.get("message")
        or data.get("msg")
    )
    
    # Check for error codes
    code = body.get("code") or data.get("code")
    is_error_code = False
    if code:
        if isinstance(code, int) and code != 200:
            is_error_code = True
        elif isinstance(code, str) and code.lower() not in ("success", "ok", "200"):
            is_error_code = True
    
    if is_error_code:
        if not fail_msg:
            fail_msg = body.get("message") or data.get("message") or body.get("msg") or data.get("msg") or f"Error code: {code}"
        if status == "processing":
            status = "fail"
    
    # Common patterns for result URLs
    if isinstance(body.get("output"), dict) and isinstance(body["output"].get("image_urls"), list):
        result_urls = body["output"]["image_urls"]
    elif isinstance(data.get("output"), dict) and isinstance(data["output"].get("image_urls"), list):
        result_urls = data["output"]["image_urls"]
    elif isinstance(body.get("image_urls"), list):
        result_urls = body["image_urls"]

    entry = _nano_tasks.get(task_id, {"provider": "nano"})
    entry.update({"status": status, "callback": body})
    if fail_msg:
        entry["error"] = fail_msg
    if result_urls:
        entry["result_image_url"] = result_urls[0]
    _nano_tasks[task_id] = entry
    
    logger.info("nano_callback_received", task_id=task_id, status=status, has_error=bool(fail_msg), error_msg=fail_msg[:100] if fail_msg else None)
    
    return {"ok": True}


@router.get("/status")
async def get_status(task_id: str):
    entry = _nano_tasks.get(task_id, {"provider": "nano"})
    status = entry.get("status", "processing")

    # Fallback: if we don't yet have a result and status is not already failed, query provider directly
    # Don't query if status is already "fail" - trust the callback
    if status not in ("success", "completed", "fail") or not entry.get("result_image_url"):
        try:
            info = await NanoBananaProvider.query_task(task_id)
            # Expected shape (per docs): { code, msg, data: { state, resultJson, ... } }
            code = info.get("code") if isinstance(info, dict) else None
            
            # Check for error codes
            is_error_code = False
            if code:
                if isinstance(code, int) and code != 200:
                    is_error_code = True
                elif isinstance(code, str) and str(code).lower() not in ("success", "ok", "200"):
                    is_error_code = True
            
            if is_error_code:
                fail_msg = info.get("msg") or info.get("message") or f"Error code: {code}"
                entry["status"] = "fail"
                entry["error"] = fail_msg
                _nano_tasks[task_id] = entry
            else:
                data = (info or {}).get("data") or {}
                state = data.get("state") or data.get("status") or info.get("status") or status
                
                # Normalize state values
                state_str = str(state).lower() if state else None
                if state_str in ("fail", "failed", "error", "failure"):
                    state = "fail"
                elif state_str in ("success", "completed", "done", "finish"):
                    state = "success"
                elif state_str in ("pending", "processing", "generating", "running"):
                    state = "processing"
                
                entry["status"] = state
                
                # Capture failure info if provided
                fail_msg = (
                    data.get("failMsg") 
                    or data.get("failMessage") 
                    or data.get("message")
                    or data.get("msg")
                    or (info or {}).get("msg")
                    or (info or {}).get("message")
                )
                if fail_msg:
                    entry["error"] = fail_msg
                
                # Parse resultJson if present
                result_json = data.get("resultJson")
                if isinstance(result_json, str) and result_json.strip():
                    import json as _json
                    try:
                        parsed = _json.loads(result_json)
                        urls = parsed.get("resultUrls") or parsed.get("image_urls") or []
                        if isinstance(urls, list) and urls:
                            entry["result_image_url"] = urls[0]
                    except Exception:
                        pass
                _nano_tasks[task_id] = entry
        except Exception as e:
            # Log errors but don't fail if task is still processing
            import structlog
            logger = structlog.get_logger("bould")
            logger.warning("status_query_error", task_id=task_id, error=str(e))
            # Only update if we don't have a status yet
            if status == "processing" and not entry.get("error"):
                pass  # Keep processing status

    out: Dict[str, Any] = {
        "task_id": task_id,
        "status": entry.get("status", "processing"),
        "provider": entry.get("provider", "nano"),
    }
    url = entry.get("result_image_url")
    if url:
        # Absolute URL passthrough
        out["result_image_url"] = url if url.startswith("http") else f"{settings.public_base_url.rstrip('/')}{url}"
    if entry.get("error"):
        out["error"] = entry["error"]
    return out
