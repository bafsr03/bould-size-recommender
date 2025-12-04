import pytest
from app.services.recommender import Recommender

@pytest.mark.asyncio
async def test_recommender_v2_strict_cm():
    """
    Verify strict CM matching.
    """
    recommender = Recommender()
    
    # Garment Scale (Dual Unit, Girth)
    garment_scale = {
        "units": ["cm", "inch"],
        "scale_cm": {
            "M": {"chest": 100.0, "waist": 80.0}
        },
        "scale_in": {
            "M": {"chest": 39.37, "waist": 31.5}
        }
    }
    
    # User Body (CM)
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
async def test_recommender_v2_strict_inch():
    """
    Verify strict Inch matching.
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
    
    # User Body (Inch)
    body_in = {"chest": 40.0, "waist": 32.0}
    
    result = await recommender.recommend(
        body_measurements=body_in,
        garment_scale=garment_scale,
        garment_category_id=3,
        user_unit="inch"
    )
    
    assert result["recommended_size"] == "M"
    assert result["match_details"]["unit"] == "inch"
    assert abs(result["match_details"]["slacks"]["chest"]) < 1.0

@pytest.mark.asyncio
async def test_recommender_v2_no_cross_talk():
    """
    Verify that Inch body is NOT compared to CM scale.
    """
    recommender = Recommender()
    
    garment_scale = {
        "units": ["cm", "inch"],
        "scale_cm": {
            "M": {"chest": 100.0} # CM
        },
        "scale_in": {
            "M": {"chest": 40.0} # Inch
        }
    }
    
    # User Body (Inch) - 40.0
    # If compared to CM scale (100.0), slack would be 60.0 (Huge!)
    # If compared to Inch scale (40.0), slack is 0.0 (Perfect)
    body_in = {"chest": 40.0}
    
    result = await recommender.recommend(
        body_measurements=body_in,
        garment_scale=garment_scale,
        garment_category_id=3,
        user_unit="inch"
    )
    
    assert result["recommended_size"] == "M"
    assert result["match_details"]["unit"] == "inch"
    assert abs(result["match_details"]["slacks"]["chest"]) < 1.0
