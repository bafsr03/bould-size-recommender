import json
from typing import Dict, Any, List, Tuple
from ..config import settings
from .llm import TailorLLM


SIZE_ORDER: List[str] = ["XXS", "XS", "S", "M", "L", "XL", "XXL", "3XL", "4XL", "5XL", "6XL"]

# Weights for scoring (higher = more important)
METRIC_WEIGHTS = {
    "chest": 2.0,
    "waist": 1.5,
    "hips": 1.5,
    "shoulder_width": 1.2,
    "default": 1.0
}

# Target ease (optimal slack) in CM
TARGET_EASE_CM = {
    "chest": 2.0,
    "waist": 4.0,
    "hips": 4.0,
    "shoulder_width": 1.5,
    "default": 2.0
}

# Tolerance for negative slack (tightness) before severe penalty
NEGATIVE_TOLERANCE_CM = 1.0

def _metrics_for_category(category_id: int) -> List[str]:
    upper = {3, 4, 5, 6, 7, 8, 9, 10}
    lower = {1, 2, 11, 12}
    dress = {13}
    if category_id in upper:
        return ["chest", "waist", "shoulder_width", "sleeve_length"]
    if category_id in lower:
        return ["waist", "hips", "inseam", "thigh"]
    if category_id in dress:
        return ["chest", "waist", "hips", "length"]
    return ["chest", "waist", "hips"]


def _get_metric_weight(metric: str, category_id: int) -> float:
    m = metric.lower()
    return METRIC_WEIGHTS.get(m, METRIC_WEIGHTS["default"])


def _get_target_ease(metric: str, category_id: int, unit: str) -> float:
    m = metric.lower()
    val_cm = TARGET_EASE_CM.get(m, TARGET_EASE_CM["default"])
    if m == "waist" and category_id in {1, 2, 11, 12}:
        val_cm = 2.0
        
    if unit == "inch":
        return val_cm / 2.54
    return val_cm


def _score_size(relevant_metrics: List[str], body: Dict[str, float], garment: Dict[str, float], category_id: int, unit: str) -> Tuple[float, Dict[str, float]]:
    total_score = 0.0
    details: Dict[str, float] = {}
    
    for m in relevant_metrics:
        b = body.get(m)
        g = garment.get(m)
        if b is None or g is None:
            continue
            
        weight = _get_metric_weight(m, category_id)
        target_ease = _get_target_ease(m, category_id, unit)
        
        # Actual slack in native unit
        slack = g - b
        details[m] = slack
        
        # Deviation from target ease
        deviation = slack - target_ease
        
        # Convert to CM for consistent penalty scoring
        # If unit is inch, slack_cm = slack * 2.54
        slack_cm = slack * 2.54 if unit == "inch" else slack
        deviation_cm = deviation * 2.54 if unit == "inch" else deviation
        
        if deviation < 0:
            # Too tight
            if slack_cm < -NEGATIVE_TOLERANCE_CM:
                # Negative slack beyond tolerance (very bad)
                penalty = abs(slack_cm) * 10.0 * weight 
            else:
                # Positive slack but less than target
                penalty = abs(deviation_cm) * 2.0 * weight
        else:
            # Too loose
            penalty = abs(deviation_cm) * 1.0 * weight
            
        total_score += penalty
        
    return total_score, details


class Recommender:
    def __init__(self, default_unit: str = "cm") -> None:
        self.llm = TailorLLM()
        self.default_unit = default_unit

    async def recommend(
        self,
        body_measurements: Dict[str, float],
        garment_scale: Dict[str, Any],
        garment_category_id: int,
        brand_scale: Dict[str, Any] | None = None,
        tone: str | None = None,
        user_unit: str = "cm",
    ) -> Dict[str, Any]:
        
        # V2 Logic: Strict Unit Matching
        # We assume the garment scale has explicit 'scale_cm' and 'scale_in' keys.
        # We assume body_measurements are already in 'user_unit'.
        
        table = {}
        calc_unit = user_unit
        
        # Helper to normalize keys (lowercase, map aliases)
        def _norm_keys(t: Dict[str, Any]) -> Dict[str, Any]:
            out = {}
            for s, m in t.items():
                out[s] = {}
                for k, v in m.items():
                    k_norm = k.lower()
                    if k_norm == "shoulder_to_shoulder": k_norm = "shoulder_width"
                    # Map hem to hips as they are often used interchangeably for bottom width
                    if k_norm == "hem": k_norm = "hips"
                    out[s][k_norm] = float(v)
            return out

        # 1. Select Table
        if brand_scale:
            # Legacy support for brand charts (assume CM unless specified)
            # Ideally brand charts should also be dual-unit V2.
            # For now, we'll do a quick legacy normalization if it's old format.
            # But if it has scale_cm/scale_in, we use that.
            if user_unit == "inch" and "scale_in" in brand_scale:
                table = _norm_keys(brand_scale["scale_in"])
                calc_unit = "inch"
            elif user_unit == "cm" and "scale_cm" in brand_scale:
                table = _norm_keys(brand_scale["scale_cm"])
                calc_unit = "cm"
            else:
                # Fallback: Assume brand scale is CM and normalize
                # This is the only place we might need conversion if data is old
                raw_scale = brand_scale.get("scale", {})
                table = _norm_keys(raw_scale)
                calc_unit = "cm" # Assume CM for legacy brand charts
        else:
            # Garment Scale from Pipeline
            if user_unit == "inch" and "scale_in" in garment_scale:
                table = _norm_keys(garment_scale["scale_in"])
                calc_unit = "inch"
            elif user_unit == "cm" and "scale_cm" in garment_scale:
                table = _norm_keys(garment_scale["scale_cm"])
                calc_unit = "cm"
            else:
                # Fallback for old pipeline data
                raw_scale = garment_scale.get("scale", {})
                table = _norm_keys(raw_scale)
                # Try to guess unit from metadata, default to CM
                declared = garment_scale.get("unit", "cm").lower()
                if declared in ("inch", "inches", "in"):
                    calc_unit = "inch"
                else:
                    calc_unit = "cm"

        # 2. Prepare Body
        # If calc_unit matches user_unit, use body as is.
        # If mismatch (fallback case), convert body to calc_unit.
        body_calc = body_measurements.copy()
        if user_unit == "inch" and calc_unit == "cm":
            body_calc = {k: v * 2.54 for k, v in body_measurements.items()}
        elif user_unit == "cm" and calc_unit == "inch":
            body_calc = {k: v / 2.54 for k, v in body_measurements.items()}
            
        # 3. Auto-Detect / Validate Category
        # Heuristic: Check if the garment keys match the expected metrics for the category.
        # If not, try to find a better category match.
        
        # Get all keys present in the garment table (using the first available size)
        garment_keys = set()
        if table:
            first_size = next(iter(table))
            garment_keys = set(table[first_size].keys())

        expected_metrics = set(_metrics_for_category(garment_category_id))
        
        # Calculate overlap with current category
        current_overlap = len(garment_keys.intersection(expected_metrics))
        
        # Check alternative: If current is Lower (1), check Upper (3). If Upper (3), check Lower (1).
        # We use 3 (Top) and 1 (Pants) as representatives.
        alt_category_id = 3 if garment_category_id in {1, 2, 11, 12} else 1
        alt_metrics = set(_metrics_for_category(alt_category_id))
        alt_overlap = len(garment_keys.intersection(alt_metrics))
        
        # If alternative has significantly better overlap, switch.
        # "Significantly" means at least 2 more matching keys, or if current has 0/1 and alt has 2+.
        if alt_overlap > current_overlap + 1:
            print(f"DEBUG: Auto-Switching Category from {garment_category_id} to {alt_category_id} based on keys {garment_keys}")
            garment_category_id = alt_category_id
            
        relevant = _metrics_for_category(garment_category_id)

        print(f"DEBUG: V2 Recommender | User Unit: {user_unit} | Calc Unit: {calc_unit}")
        print(f"DEBUG: Body: {body_calc}")
        print(f"DEBUG: Garment Table: {table}")
        
        best_size = None
        best_score = float("inf")
        best_details: Dict[str, float] = {}

        for size in SIZE_ORDER:
            if size not in table:
                continue
            
            score, details = _score_size(relevant, body_calc, table[size], garment_category_id, calc_unit)
            
            if score < best_score:
                best_score = score
                best_size = size
                best_details = details

        if best_size is None:
             for s in SIZE_ORDER:
                if s in table:
                    best_size = s
                    break

        confidence = max(0.0, 1.0 - (best_score / 100.0))
        
        # Critical failure check (using CM threshold)
        critical_metrics = ["chest", "waist", "hips"]
        for m in critical_metrics:
            if m in best_details:
                slack_cm = best_details[m] * 2.54 if calc_unit == "inch" else best_details[m]
                if slack_cm < -2.0:
                    confidence *= 0.8

        tailor_feedback_data = await self.llm.generate_feedback(
            category_id=garment_category_id,
            body=body_calc, # Pass used body measurements
            garment=table.get(best_size, {}),
            slacks=best_details,
            size=best_size or "",
            tone=tone,
        )

        final_feedback = tailor_feedback_data.get("final", "")
        preview_feedback = tailor_feedback_data.get("preview", [])

        return {
            "recommended_size": best_size or "",
            "confidence": round(confidence, 3),
            "match_details": {"slacks": best_details, "unit": calc_unit},
            "tailor_feedback": final_feedback,
            "preview_feedback": preview_feedback,
            "final_feedback": final_feedback,
        }

