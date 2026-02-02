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

# Height-based minimum size guardrails (cm)
# For users above this height, enforce minimum size unless explicitly tight fit
HEIGHT_GUARDRAILS = {
    183: {  # 6'0" = 183cm
        "min_size": "L",
        "min_chest": 95.0,
        "min_shoulder": 42.0,
    },
    190: {  # 6'3" = 190cm
        "min_size": "XL",
        "min_chest": 98.0,
        "min_shoulder": 44.0,
    },
}

# Confidence thresholds
MIN_CONFIDENCE_THRESHOLD = 0.3  # Below this, recommendation is unreliable
WARNING_CONFIDENCE_THRESHOLD = 0.5  # Below this, show warning


def get_height_based_size_range(height_cm: float, is_lean: bool = False) -> Tuple[str, str]:
    """
    Get recommended size range based on height.
    Returns (min_size, max_size) tuple.
    
    Height ranges:
    - Under 5'5" (165cm): XS to S
    - 5'5" to 5'8" (165-173cm): S to L
    - 5'7" to 5'10" (170-178cm): M to L
    - 5'11" to 6'2" (180-188cm): L to XL
    - Over 6'2" (188cm+): XL to up, unless lean
    """
    if height_cm < 165:  # Under 5'5"
        return ("XS", "S")
    elif height_cm < 170:  # 5'5" to 5'7" (exclusive of 5'7")
        return ("S", "L")
    elif height_cm < 178:  # 5'7" to 5'10"
        return ("M", "L")
    elif height_cm < 188:  # 5'11" to 6'2"
        return ("L", "XL")
    else:  # Over 6'2"
        if is_lean:
            return ("L", "XL")  # Lean users may fit in L-XL
        else:
            return ("XL", "XXL")  # Standard to larger builds need XL+


def detect_lean_body_type(body_measurements: Dict[str, float], height_cm: float) -> bool:
    """
    Detect if user has a lean body type based on measurements.
    A lean body type is characterized by:
    - Lower chest-to-height ratio
    - Lower waist-to-height ratio
    - Higher shoulder-to-waist ratio (more V-shaped)
    """
    chest = body_measurements.get("chest")
    waist = body_measurements.get("waist")
    
    if not chest or not waist or not height_cm:
        return False
    
    # Calculate ratios
    chest_to_height = chest / height_cm
    waist_to_height = waist / height_cm
    
    # Lean thresholds (empirically determined)
    # Average chest-to-height: ~0.55, lean: < 0.53
    # Average waist-to-height: ~0.47, lean: < 0.45
    is_lean = (chest_to_height < 0.53) and (waist_to_height < 0.45)
    
    return is_lean


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


def _score_size(relevant_metrics: List[str], body: Dict[str, float], garment: Dict[str, float], category_id: int, unit: str) -> Tuple[float, Dict[str, float], Dict[str, Any]]:
    """
    Score a size based on body vs garment measurements.
    Returns: (total_score, details_dict, debug_info)
    """
    total_score = 0.0
    details: Dict[str, float] = {}
    missing_metrics: List[str] = []
    scored_metrics: List[str] = []

    for m in relevant_metrics:
        b = body.get(m)
        g = garment.get(m)
        if b is None or g is None:
            missing_metrics.append(m)
            continue
        
        scored_metrics.append(m)
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
    
    # CRITICAL FIX: Penalize missing critical metrics
    # Missing metrics mean we can't properly evaluate the size
    # Apply penalty based on importance of missing metrics
    missing_penalty = 0.0
    for m in missing_metrics:
        weight = _get_metric_weight(m, category_id)
        # Penalty: 50 points per missing metric, weighted by importance
        missing_penalty += 50.0 * weight
    
    total_score += missing_penalty
    
    debug_info = {
        "scored_metrics": scored_metrics,
        "missing_metrics": missing_metrics,
        "missing_penalty": missing_penalty,
    }
    
    return total_score, details, debug_info


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
        height_cm: float | None = None,  # Optional height for guardrails
        debug: bool = False,  # Enable debug output
    ) -> Dict[str, Any]:

        # Normalize user_unit
        user_unit = user_unit.lower().strip()
        if user_unit in ("inches", "in", "feet", "ft"):
            user_unit = "inch"

        # CHART_TYPE VALIDATION: Fail fast if chart_type is missing (unless legacy data)
        chart_type = None
        if brand_scale:
            chart_type = brand_scale.get("chart_type")
        else:
            chart_type = garment_scale.get("chart_type")
        
        # For new data, chart_type is required
        # For legacy data (no chart_type), default to "garment" but log warning
        if chart_type is None:
            # Legacy support: default to "garment" for backward compatibility
            chart_type = "garment"
            if debug:
                print("WARNING: chart_type missing, defaulting to 'garment'")
        elif chart_type not in ("garment", "body"):
            raise ValueError(f"Invalid chart_type: {chart_type}. Must be 'garment' or 'body'")
        
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

        # HEIGHT-BASED GUARDRAILS: Validate body measurements make sense for height
        guardrail_min_size = None
        guardrail_reason = None
        if height_cm is not None:
            # Find applicable guardrail
            for threshold_height in sorted(HEIGHT_GUARDRAILS.keys(), reverse=True):
                if height_cm >= threshold_height:
                    guardrail = HEIGHT_GUARDRAILS[threshold_height]
                    guardrail_min_size = guardrail["min_size"]
                    
                    # Check if body measurements meet minimums
                    chest = body_calc.get("chest")
                    shoulder = body_calc.get("shoulder_width")
                    
                    if chest and chest < guardrail["min_chest"]:
                        guardrail_reason = f"chest {chest}cm below minimum {guardrail['min_chest']}cm for {height_cm}cm height"
                    elif shoulder and shoulder < guardrail["min_shoulder"]:
                        guardrail_reason = f"shoulder {shoulder}cm below minimum {guardrail['min_shoulder']}cm for {height_cm}cm height"
                    else:
                        guardrail_reason = f"height {height_cm}cm requires minimum size {guardrail_min_size}"
                    break

        # HEIGHT-BASED SIZE RANGE: Get recommended range based on height
        height_size_range = None
        is_lean = False
        if height_cm is not None:
            is_lean = detect_lean_body_type(body_calc, height_cm)
            height_size_range = get_height_based_size_range(height_cm, is_lean)
        
        if debug:
            print(f"DEBUG: V2 Recommender | User Unit: {user_unit} | Calc Unit: {calc_unit}")
            print(f"DEBUG: Chart Type: {chart_type}")
            print(f"DEBUG: Body: {body_calc}")
            print(f"DEBUG: Height: {height_cm}cm" if height_cm else "DEBUG: Height: not provided")
            print(f"DEBUG: Lean Body Type: {is_lean}")
            print(f"DEBUG: Height-Based Range: {height_size_range}" if height_size_range else "DEBUG: Height Range: none")
            print(f"DEBUG: Guardrail: {guardrail_min_size}" if guardrail_min_size else "DEBUG: Guardrail: none")
            print(f"DEBUG: Garment Table: {table}")
        
        best_size = None
        best_score = float("inf")
        best_details: Dict[str, float] = {}
        all_scores_debug: Dict[str, Dict[str, Any]] = {}  # For debug output

        # Determine which sizes to consider based on height range
        sizes_to_consider = SIZE_ORDER
        if height_size_range:
            min_size, max_size = height_size_range
            min_idx = SIZE_ORDER.index(min_size) if min_size in SIZE_ORDER else 0
            max_idx = SIZE_ORDER.index(max_size) if max_size in SIZE_ORDER else len(SIZE_ORDER) - 1
            
            # STRICT MODE: Do not allow slack outside the range
            # We strictly clip to the recommended range
            sizes_to_consider = SIZE_ORDER[min_idx:max_idx + 1]
            
            if debug:
                print(f"DEBUG: Constrained sizes to: {sizes_to_consider}")

        for size in sizes_to_consider:
            if size not in table:
                continue
            
            score, details, score_debug = _score_size(relevant, body_calc, table[size], garment_category_id, calc_unit)
            
            # Apply bonus for sizes within the height-based range
            if height_size_range:
                min_size, max_size = height_size_range
                if min_size in SIZE_ORDER and max_size in SIZE_ORDER:
                    min_idx = SIZE_ORDER.index(min_size)
                    max_idx = SIZE_ORDER.index(max_size)
                    size_idx = SIZE_ORDER.index(size)
                    if min_idx <= size_idx <= max_idx:
                        # Size is within recommended range, apply small bonus
                        score *= 0.95  # 5% bonus for being in height-recommended range
            
            if debug:
                all_scores_debug[size] = {
                    "score": score,
                    "deltas": details,
                    "missing_metrics": score_debug.get("missing_metrics", []),
                    "scored_metrics": score_debug.get("scored_metrics", []),
                }
            
            if score < best_score:
                best_score = score
                best_size = size
                best_details = details

        if best_size is None:
             for s in SIZE_ORDER:
                if s in table:
                    best_size = s
                    break

        # IMPROVED CONFIDENCE CALCULATION
        # Base confidence from score
        base_confidence = max(0.0, 1.0 - (best_score / 100.0))

        # Penalize for missing critical metrics
        critical_metrics = ["chest", "waist", "hips"]
        missing_critical = [m for m in critical_metrics if m not in best_details]
        if missing_critical:
            # Reduce confidence by 20% per missing critical metric
            base_confidence *= (1.0 - 0.2 * len(missing_critical))
        
        # Critical failure check (using CM threshold)
        for m in critical_metrics:
            if m in best_details:
                slack_cm = best_details[m] * 2.54 if calc_unit == "inch" else best_details[m]
                if slack_cm < -2.0:
                    base_confidence *= 0.8
        
        confidence = max(0.0, min(1.0, base_confidence))
        
        # APPLY HEIGHT GUARDRAILS: Enforce minimum size for tall users
        reason_codes = []
        if guardrail_min_size and best_size:
            # Check if recommended size violates guardrail
            size_order_idx = SIZE_ORDER.index(best_size) if best_size in SIZE_ORDER else -1
            min_size_idx = SIZE_ORDER.index(guardrail_min_size) if guardrail_min_size in SIZE_ORDER else -1
            
            if size_order_idx >= 0 and min_size_idx >= 0 and size_order_idx < min_size_idx:
                # Recommended size is smaller than minimum
                if tone and tone.lower() in ("tight", "slim", "fitted"):
                    # Allow if user explicitly wants tight fit
                    reason_codes.append("GUARDRAIL_OVERRIDE_TIGHT_FIT")
                else:
                    # Enforce minimum size
                    old_size = best_size
                    best_size = guardrail_min_size
                    reason_codes.append(f"GUARDRAIL_ENFORCED_{old_size}_TO_{guardrail_min_size}")
                    
                    # Recalculate for enforced size
                    if best_size in table:
                        score, details, _ = _score_size(relevant, body_calc, table[best_size], garment_category_id, calc_unit)
                        best_score = score
                        best_details = details
                        # Reduce confidence due to guardrail enforcement
                        confidence *= 0.85
                        reason_codes.append(f"GUARDRAIL_REASON_{guardrail_reason}")
        
        # CONFIDENCE THRESHOLD: If confidence too low, add warning or fallback
        if confidence < MIN_CONFIDENCE_THRESHOLD:
            reason_codes.append("LOW_CONFIDENCE")
            # Fallback: Recommend size range instead of single size
            # Or ask for additional measurements
            if debug:
                print(f"WARNING: Confidence {confidence} below threshold {MIN_CONFIDENCE_THRESHOLD}")
        elif confidence < WARNING_CONFIDENCE_THRESHOLD:
            reason_codes.append("CONFIDENCE_WARNING")

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

        result = {
            "recommended_size": best_size or "",
            "confidence": round(confidence, 3),
            "match_details": {"slacks": best_details, "unit": calc_unit},
            "tailor_feedback": final_feedback,
            "preview_feedback": preview_feedback,
            "final_feedback": final_feedback,
        }
        
        # DEBUG OUTPUT: Only include if debug flag is set
        if debug:
            result["debug"] = {
                "normalized_units": {
                    "user_unit": user_unit,
                    "calc_unit": calc_unit,
                },
                "chart_type": chart_type,
                "body_metrics_used": body_calc,
                "garment_scale_used": {k: list(v.keys()) for k, v in table.items()},
                "per_size_deltas": {size: all_scores_debug.get(size, {}).get("deltas", {}) for size in SIZE_ORDER if size in table},
                "per_size_scores": {size: all_scores_debug.get(size, {}).get("score", 0) for size in SIZE_ORDER if size in table},
                "chosen_size": best_size,
                "chosen_score": best_score,
                "confidence": round(confidence, 3),
                "reason_codes": reason_codes,
                "height_cm": height_cm,
                "guardrail_applied": guardrail_min_size if guardrail_min_size else None,
                "relevant_metrics": relevant,
                "category_id": garment_category_id,
            }
        
        return result

