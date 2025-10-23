import os
import tempfile
import httpx
from typing import Optional
from fastapi import APIRouter, Depends, File, Form, UploadFile, HTTPException
from fastapi.responses import FileResponse, Response

from ..security import verify_api_key
from ..services.garment_api import GarmentApiClient
from ..config import settings


router = APIRouter(prefix="/process", tags=["process"], dependencies=[Depends(verify_api_key)])


@router.post("")
async def process(
    image: UploadFile = File(...),
    category_id: int = Form(...),
    true_size: str = Form(...),
    true_waist: Optional[float] = Form(None),
    unit: str = Form("cm"),
):
    """
    Direct process endpoint that calls the garments API and returns the raw results.
    This is used by the converter to get measurement visualization and size scale.
    """
    if image.content_type is None or not image.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Please upload an image file")

    garment_client = GarmentApiClient()

    # Save uploaded image to temporary file
    with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(image.filename or "garment.jpg")[1] or ".jpg") as tmp:
        content = await image.read()
        tmp.write(content)
        garment_path = tmp.name

    try:
        # Call garment API directly
        garment_result = await garment_client.process_image(
            image_path=garment_path,
            category_id=category_id,
            true_size=true_size,
            unit=unit,
        )
        
        # Return the raw result from garments API
        return garment_result
        
    finally:
        try:
            os.remove(garment_path)
        except Exception:
            pass


@router.get("/file")
async def get_file(path: str, _=Depends(verify_api_key)):
    """
    Serve files from the garments API storage directory.
    This is used to serve measurement visualization images and size scale JSON files.
    """
    try:
        # Get token for garments API
        garment_client = GarmentApiClient()
        token = await garment_client._ensure_token()
        
        # Construct the file URL on the garments API
        garments_base = settings.garments_api_base.rstrip("/")
        file_url = f"{garments_base}/files?path={path}"
        
        # Fetch the file from garments API
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                file_url,
                headers={"Authorization": f"Bearer {token}"}
            )
            response.raise_for_status()
            
            # Determine content type
            content_type = response.headers.get("content-type", "application/octet-stream")
            
            # Return the file content
            return Response(
                content=response.content,
                media_type=content_type,
                headers={
                    "Cache-Control": "public, max-age=3600"
                }
            )
            
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            raise HTTPException(status_code=404, detail="File not found")
        else:
            raise HTTPException(status_code=e.response.status_code, detail=f"Error fetching file: {e.response.text}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error serving file: {str(e)}")
