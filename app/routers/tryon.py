import os
import tempfile
from typing import Optional, List
from fastapi import APIRouter, Depends, File, UploadFile, HTTPException, Body, Form

from ..security import verify_api_key
from ..services.vto_providers import get_provider
from ..services.vto_providers.nanobanana import NanoBananaProvider
from ..config import settings


router = APIRouter(prefix="/try-on", tags=["try-on"], dependencies=[Depends(verify_api_key)])


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
        payload = await provider.create_task(
            prompt="Generate a try-on image",
            image_urls=[public_user, public_garment],
            callback_url=callback_url,
            output_format="png",
            image_size="1:1",
        )
        return {"success": True, "provider": "nano", "task": payload}

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
