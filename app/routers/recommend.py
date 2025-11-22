import os
import json
import tempfile
from typing import Optional, Dict, Any
from fastapi import APIRouter, Depends, File, Form, UploadFile, HTTPException

from ..security import verify_api_key
from ..services.body_api import BodyApiClient
from ..services.garment_api import GarmentApiClient
from ..services.recommender import Recommender
from ..config import settings
from ..schemas.recommend import RecommendResponse


router = APIRouter(prefix="/recommend", tags=["recommend"], dependencies=[Depends(verify_api_key)])


@router.post("")
async def recommend(
    # User measurements path A: provide numbers directly
    measurements_json: Optional[str] = Form(None),
    # or path B: provide height + image and we will call Body API
    height: Optional[float] = Form(None),
    user_image: Optional[UploadFile] = File(None),
    # Garment inputs (required)
    garment_image: UploadFile = File(...),
    category_id: int = Form(...),
    true_size: str = Form(...),
    unit: str = Form("cm"),
    brand_chart_json: Optional[str] = Form(None),
    tone: Optional[str] = Form(None),
) -> RecommendResponse:
    body_client = BodyApiClient()
    garment_client = GarmentApiClient()
    recommender = Recommender(default_unit=settings.recommender_unit)

    # Correlation ID propagation to downstream services (best-effort for dev)
    # If running under ASGI, prefer context vars; here, simple env override for local testing
    # Callers (Shopify app) can send X-Correlation-ID header which we mirror via env for clients
    # Note: this is non-threadsafe in prod; for production, pass headers explicitly via clients
    # Using env only as dev convenience
    #
    # Obtain body measurements
    body_measurements: Dict[str, float]
    test_fast = os.getenv("TEST_FAST", "0") == "1"
    if measurements_json:
        try:
            parsed = json.loads(measurements_json)
            if not isinstance(parsed, dict):
                raise ValueError
            body_measurements = {k: float(v) for k, v in parsed.items() if v is not None}
        except Exception:
            raise HTTPException(status_code=400, detail="measurements_json must be a JSON object of numeric values")
    elif test_fast:
        if height is None:
            raise HTTPException(status_code=400, detail="height required for TEST_FAST mode")
        # Create a quick synthetic measurement profile from height for local testing
        h = float(height)
        body_measurements = {
            "chest": round(h * 0.52, 2),
            "waist": round(h * 0.45, 2),
            "hips": round(h * 0.54, 2),
            "shoulder_width": round(h * 0.24, 2),
            "sleeve_length": round(h * 0.32, 2),
            "inseam": round(h * 0.45, 2),
            "thigh": round(h * 0.31, 2),
            "length": round(h * 0.62, 2),
        }
    else:
        if height is None or user_image is None:
            raise HTTPException(status_code=400, detail="Provide either measurements_json or both height and user_image")
        with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(user_image.filename or "user.jpg")[1] or ".jpg") as tmp:
            tmp.write(await user_image.read())
            tmp_path = tmp.name
        try:
            body_measurements = await body_client.analyze_file(height, tmp_path)
        finally:
            try:
                os.remove(tmp_path)
            except Exception:
                pass

    # Call garment API
    with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(garment_image.filename or "garment.jpg")[1] or ".jpg") as gtmp:
        gtmp.write(await garment_image.read())
        garment_path = gtmp.name
    try:
        garment_result = await garment_client.process_image(
            image_path=garment_path,
            category_id=category_id,
            true_size=true_size,
            unit=unit,
        )
    finally:
        try:
            os.remove(garment_path)
        except Exception:
            pass

    size_scale_path = garment_result.get("size_scale")
    measurement_vis = garment_result.get("measurement_vis")
    if not size_scale_path:
        raise HTTPException(status_code=502, detail="Garment API did not return a valid size scale")

    try:
        # Read the JSON via garments API /files endpoint (container-safe)
        size_scale = await garment_client.read_json_file(size_scale_path)
    except Exception:
        raise HTTPException(status_code=502, detail="Failed to read size scale JSON from garment API output")

    brand_chart = None
    if brand_chart_json:
        try:
            brand_chart = json.loads(brand_chart_json)
        except Exception:
            raise HTTPException(status_code=400, detail="brand_chart_json must be a JSON object")

    result = await recommender.recommend(
        body_measurements=body_measurements,
        garment_scale=size_scale,
        garment_category_id=category_id,
        brand_scale=brand_chart,
        tone=tone,
    )

    return RecommendResponse(
        recommended_size=result["recommended_size"],
        confidence=result["confidence"],
        match_details=result["match_details"],
        tailor_feedback=result["tailor_feedback"],
        debug={
            "measurement_vis_url": measurement_vis or "",
            "size_scale_unit": size_scale.get("unit", ""),
        },
    )

