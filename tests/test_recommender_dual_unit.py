import pytest
from app.services.recommender import Recommender

@pytest.mark.asyncio
async def test_recommend_strict_inch():
    """
    Verify that when user selects 'inch', the recommender uses the 'scale_in' table
    and expects body measurements in inches.
    """
    recommender = Recommender()
    
    # Mock dual-unit scale
    garment_scale = {
        "units": ["cm", "inch"],
        "scale_cm": {
            "M": {"chest": 100.0, "waist": 80.0} # CM
        },
        "scale_in": {
            "M": {"chest": 40.0, "waist": 32.0} # Inch (approx 101.6cm, 81.28cm)
        },
        "unit": "cm",
        "scale": {"M": {"chest": 100.0, "waist": 80.0}} # Legacy
    }
    
    # User body in Inches (Chest 40, Waist 32) -> Perfect match for M in inches
    body_in = {"chest": 40.0, "waist": 32.0}
    
    result = await recommender.recommend(
        body_measurements=body_in,
        garment_scale=garment_scale,
        garment_category_id=3, # Top
        user_unit="inch"
    )
    
    assert result["recommended_size"] == "M"
    assert result["match_details"]["unit"] == "inch"
    # Slack should be near 0
    assert abs(result["match_details"]["slacks"]["chest"]) < 1.0

@pytest.mark.asyncio
async def test_recommend_strict_cm():
    """
    Verify that when user selects 'cm', the recommender uses the 'scale_cm' table.
    """
    recommender = Recommender()
    
    garment_scale = {
        "units": ["cm", "inch"],
        "scale_cm": {
            "M": {"chest": 100.0, "waist": 80.0}
        },
        "scale_in": {
            "M": {"chest": 40.0, "waist": 32.0}
        }
    }
    
    # User body in CM (Chest 100, Waist 80) -> Perfect match for M in CM
    body_cm = {"chest": 100.0, "waist": 80.0}
    
    result = await recommender.recommend(
        body_measurements=body_cm,
        garment_scale=garment_scale,
        garment_category_id=3,
        user_unit="cm"
    )
    
    assert result["recommended_size"] == "M"
    assert result["match_details"]["unit"] == "cm"
    assert abs(result["match_details"]["slacks"]["chest"]) < 1.0

@pytest.mark.asyncio
async def test_recommend_fallback_legacy():
    """
    Verify fallback to legacy behavior if dual scales are missing.
    """
    recommender = Recommender()
    
    # Legacy scale (CM)
    garment_scale = {
        "unit": "cm",
        "scale": {
            "M": {"chest": 100.0, "waist": 80.0}
        }
    }
    
    # User selects Inch, but only CM scale exists.
    # Recommender should convert body (Inch) to CM and use CM scale.
    body_in = {"chest": 39.37, "waist": 31.5} # Approx 100cm, 80cm
    
    result = await recommender.recommend(
        body_measurements=body_in,
        garment_scale=garment_scale,
        garment_category_id=3,
        user_unit="inch"
    )
    
    assert result["recommended_size"] == "M"
    assert result["match_details"]["unit"] == "cm" # Fallback uses CM
    # Slack should be calculated in CM
    # 100 - (39.37 * 2.54) ~ 0
    assert abs(result["match_details"]["slacks"]["chest"]) < 1.0
