from typing import Dict, Optional, List
from pydantic import BaseModel, Field


class BrandSizeChart(BaseModel):
    unit: str = Field("cm")
    scale: Dict[str, Dict[str, float]] = Field(default_factory=dict)


class MeasurementInput(BaseModel):
    chest: Optional[float] = None
    waist: Optional[float] = None
    hips: Optional[float] = None
    shoulder_width: Optional[float] = None
    arm_length: Optional[float] = None
    inseam: Optional[float] = None
    thigh: Optional[float] = None
    height: Optional[float] = None


class RecommendResponse(BaseModel):
    recommended_size: str
    confidence: float
    match_details: Dict[str, Dict[str, float]]
    tailor_feedback: str  # Kept for backward compatibility
    preview_feedback: List[str]
    final_feedback: str
    debug: Dict[str, str] | None = None

