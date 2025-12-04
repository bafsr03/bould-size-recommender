import pytest
from app.services.recommender import Recommender

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

@pytest.mark.asyncio
async def test_recommend_weighted_preference():
    """
    Test that the recommender prefers a size that fits the most important metric (Chest for tops)
    even if another metric (Waist) is slightly loose, over a size where Chest is tight.
    """
    rec = Recommender()
    
    # Body: Chest 104 (Large-ish), Waist 85 (Medium)
    # Garment M: Chest 104 (Tight!), Waist 86 (Perfect)
    # Garment L: Chest 112 (Good fit), Waist 94 (Loose)
    
    # Old logic might pick M because Waist is perfect and Chest "technically" fits (104 >= 104).
    # New logic should prefer L because Chest tightness is penalized more heavily than Waist looseness.
    
    body = {"chest": 104.0, "waist": 85.0, "hips": 100.0}
    scale = {
        "unit": "cm",
        "scale": {
            "M": {"chest": 104.0, "waist": 86.0, "hips": 104.0},
            "L": {"chest": 112.0, "waist": 94.0, "hips": 112.0},
        }
    }
    
    res = await rec.recommend(body, scale, garment_category_id=3) # 3 = Top
    assert res["recommended_size"] == "L"

@pytest.mark.asyncio
async def test_recommend_soft_constraint():
    """
    Test that the recommender allows a size that is *slightly* too small (within tolerance)
    if the next size up is way too big.
    """
    rec = Recommender()
    
    # Body: Chest 105
    # Garment M: Chest 104 (1cm too small)
    # Garment L: Chest 120 (15cm too big - huge!)
    
    # Old logic would strictly reject M and pick L (or fail).
    # New logic should see -1cm as acceptable penalty vs +15cm looseness.
    
    body = {"chest": 105.0, "waist": 85.0}
    scale = {
        "unit": "cm",
        "scale": {
            "M": {"chest": 104.0, "waist": 86.0},
            "L": {"chest": 120.0, "waist": 102.0},
        }
    }
    
    res = await rec.recommend(body, scale, garment_category_id=3)
    assert res["recommended_size"] == "M"

@pytest.mark.asyncio
async def test_recommend_closest_match_fallback():
    """
    Test fallback when nothing fits well.
    """
    rec = Recommender()
    
    # Body: Chest 130 (Huge)
    # Max Size XXL: Chest 128
    
    body = {"chest": 130.0, "waist": 110.0}
    scale = {
        "unit": "cm",
        "scale": {
            "XL": {"chest": 120.0, "waist": 102.0},
            "XXL": {"chest": 128.0, "waist": 110.0},
        }
    }
    
    res = await rec.recommend(body, scale, garment_category_id=3)
    assert res["recommended_size"] == "XXL"
