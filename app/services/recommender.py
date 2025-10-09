import json
from typing import Dict, Any, List, Tuple
from ..config import settings
from .llm import TailorLLM


SIZE_ORDER: List[str] = ["XS", "S", "M", "L", "XL", "XXL"]


def _to_cm(value: float, unit: str) -> float:
    u = (unit or "cm").lower()
    if u in ("cm", "centimeter", "centimeters"):
        return float(value)
    if u in ("inch", "inches", "in"):
        return float(value) * 2.54
    return float(value)


def _normalize_scale(scale_obj: Dict[str, Any]) -> Dict[str, Dict[str, float]]:
    unit = (scale_obj.get("unit") or "cm").lower()
    scale = scale_obj.get("scale") or {}
    out: Dict[str, Dict[str, float]] = {}
    for size, metrics in scale.items():
        out[size] = {k: _to_cm(v, unit) for k, v in (metrics or {}).items() if isinstance(v, (int, float))}
    return out


def _metrics_for_category(category_id: int) -> List[str]:
    upper = {3, 4, 5, 6, 7, 8, 9, 10}  # DF2 tops/jackets/sweaters/etc.
    lower = {1, 2, 11, 12}  # shorts, trousers, jeans, skirt
    dress = {13}
    if category_id in upper:
        return ["chest", "waist", "shoulder_width", "sleeve_length"]
    if category_id in lower:
        return ["waist", "hips", "inseam", "thigh"]
    if category_id in dress:
        return ["chest", "waist", "hips", "length"]
    return ["chest", "waist", "hips"]


def _ease_for_metric(metric: str, category_id: int) -> float:
    m = metric.lower()
    if m in ("chest", "bust"):
        return 6.0
    if m in ("waist",):
        return 4.0 if category_id not in {1, 2, 11, 12} else 2.0
    if m in ("hips", "hip"):
        return 4.0
    if m in ("shoulder_width", "shoulder"):
        return 1.5
    if m in ("thigh",):
        return 2.0
    if m in ("inseam", "sleeve_length", "length"):
        return 1.0
    return 0.0


def _score_size(relevant_metrics: List[str], body: Dict[str, float], garment: Dict[str, float], category_id: int) -> Tuple[bool, float, Dict[str, float]]:
    total_slack = 0.0
    details: Dict[str, float] = {}
    all_ok = True
    for m in relevant_metrics:
        b = body.get(m)
        g = garment.get(m)
        if b is None or g is None:
            continue
        ease = _ease_for_metric(m, category_id)
        slack = g - (b + ease)
        details[m] = slack
        if slack < 0:
            all_ok = False
        total_slack += max(slack, 0.0)
    return all_ok, total_slack, details


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
    ) -> Dict[str, Any]:
        # Normalize body to cm
        body_cm = {k: _to_cm(v, self.default_unit) for k, v in body_measurements.items() if isinstance(v, (int, float))}

        # Normalize garment scale and optional brand chart
        scale_cm = _normalize_scale(garment_scale)
        brand_cm = _normalize_scale(brand_scale) if brand_scale else None

        relevant = _metrics_for_category(garment_category_id)

        # Choose table to evaluate: prefer brand if provided, otherwise measurement-derived
        table = brand_cm or scale_cm

        best_size = None
        best_score = float("inf")
        best_details: Dict[str, float] = {}

        for size in SIZE_ORDER:
            if size not in table:
                continue
            ok, score, details = _score_size(relevant, body_cm, table[size], garment_category_id)
            # prefer all_ok; among ok, minimal slack; otherwise minimal violations (score stays >0 only from positive slack; we need a penalty)
            penalty = sum(-v for v in details.values() if v < 0)
            effective = (score, penalty)
            if ok:
                # prioritize ok solutions with smaller score
                if best_size is None or (best_size is not None and best_score > score):
                    best_size = size
                    best_score = score
                    best_details = details
            else:
                # no-ok yet; pick least-violating using smaller penalty
                if best_size is None:
                    best_size = size
                    best_score = score + penalty
                    best_details = details

        if best_size is None:
            # fallback to true_size if present in table else closest available
            for s in SIZE_ORDER:
                if s in table:
                    best_size = s
                    best_details = {}
                    break

        # Confidence heuristic
        violations = sum(1 for v in best_details.values() if v < 0)
        avg_slack = sum(max(v, 0.0) for v in best_details.values()) / max(len(best_details) or 1, 1)
        confidence = max(0.0, 1.0 - 0.1 * violations - 0.02 * avg_slack)

        tailor_feedback = await self.llm.generate_feedback(
            category_id=garment_category_id,
            body=body_cm,
            garment=table.get(best_size, {}),
            slacks=best_details,
            size=best_size or "",
        )

        return {
            "recommended_size": best_size or "",
            "confidence": round(confidence, 3),
            "match_details": {"slacks_cm": best_details},
            "tailor_feedback": tailor_feedback,
        }
