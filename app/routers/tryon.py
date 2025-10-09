import os
import tempfile
from typing import Optional, List
from fastapi import APIRouter, Depends, File, UploadFile, HTTPException, Body

from ..security import verify_api_key
from ..services.vto_providers import get_provider
from ..services.vto_providers.nanobanana import NanoBananaProvider
from ..config import settings


router = APIRouter(prefix="/try-on", tags=["try-on"], dependencies=[Depends(verify_api_key)])


@router.post("")
async def try_on(user_image: UploadFile = File(...), garment_image: UploadFile = File(...)):
    provider = get_provider(settings.vto_provider)
    with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(user_image.filename or "user.jpg")[1] or ".jpg") as utmp:
        utmp.write(await user_image.read())
        user_path = utmp.name
    with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(garment_image.filename or "garment.jpg")[1] or ".jpg") as gtmp:
        gtmp.write(await garment_image.read())
        garment_path = gtmp.name

    try:
        out_path = await provider.generate(user_path, garment_path)
    finally:
        try:
            os.remove(user_path)
        except Exception:
            pass
        try:
            os.remove(garment_path)
        except Exception:
            pass

    if not out_path or not os.path.exists(out_path):
        raise HTTPException(status_code=500, detail="Try-on provider failed to generate an image")

    rel_name = os.path.basename(out_path)
    url = f"/files/{rel_name}"
    return {"success": True, "provider": settings.vto_provider, "result_image_url": url}


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
