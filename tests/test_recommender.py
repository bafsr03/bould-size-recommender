import pytest
from app.services.recommender import Recommender, _normalize_scale

# Mock data
BODY_M = {
    "chest": 100.0,
    "waist": 85.0,
    "hips": 100.0,
}

# Scale in CM
SCALE_CM = {
    "unit": "cm",
    "scale": {
        "S": {"chest": 96.0, "waist": 81.0, "hips": 96.0},
        "M": {"chest": 101.0, "waist": 86.0, "hips": 101.0},
        "L": {"chest": 106.0, "waist": 91.0, "hips": 106.0},
    }
}

# Scale in Inches (Explicit)
SCALE_IN_EXPLICIT = {
    "unit": "in",
    "scale": {
        "S": {"chest": 38.0, "waist": 32.0, "hips": 38.0}, # ~96.5cm
        "M": {"chest": 40.0, "waist": 34.0, "hips": 40.0}, # ~101.6cm
        "L": {"chest": 42.0, "waist": 36.0, "hips": 42.0}, # ~106.7cm
    }
}

# Scale in Inches (Implicit/Missing Unit) - The Bug Case
SCALE_IN_IMPLICIT = {
    "unit": "cm", # Wrongly labeled as cm
    "scale": {
        "S": {"chest": 38.0, "waist": 32.0, "hips": 38.0},
        "M": {"chest": 40.0, "waist": 34.0, "hips": 40.0},
        "L": {"chest": 42.0, "waist": 36.0, "hips": 42.0},
    }
}

def test_normalize_scale_cm():
    norm = _normalize_scale(SCALE_CM)
    assert norm["M"]["chest"] == 101.0

def test_normalize_scale_inches_explicit():
    norm = _normalize_scale(SCALE_IN_EXPLICIT)
    # 40 inches * 2.54 = 101.6
    assert abs(norm["M"]["chest"] - 101.6) < 0.1

def test_normalize_scale_inches_implicit():
    # This tests the heuristic fix
    norm = _normalize_scale(SCALE_IN_IMPLICIT)
    # Should be treated as inches despite "cm" label
    assert abs(norm["M"]["chest"] - 101.6) < 0.1

@pytest.mark.asyncio
async def test_recommend_cm():
    rec = Recommender()
    res = await rec.recommend(BODY_M, SCALE_CM, garment_category_id=3)
    # Body 100, M chest 101. Fits with 1cm slack.
    # Ease for chest is 6.0. So 101 - (100+6) = -5. Not fitting?
    # Wait, let's check ease logic.
    # _ease_for_metric("chest") -> 6.0
    # slack = garment - (body + ease)
    # M: 101 - (100 + 6) = -5. Fail.
    # L: 106 - (100 + 6) = 0. Fit!
    assert res["recommended_size"] == "L"

@pytest.mark.asyncio
async def test_recommend_inches_implicit():
    rec = Recommender()
    res = await rec.recommend(BODY_M, SCALE_IN_IMPLICIT, garment_category_id=3)
    # M (inches): 40in = 101.6cm. 
    # 101.6 - (100 + 6) = -4.4. Fail.
    # L (inches): 42in = 106.68cm.
    # 106.68 - (100 + 6) = 0.68. Fit!
    assert res["recommended_size"] == "L"
