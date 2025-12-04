import pytest
from app.services.recommender import Recommender

@pytest.mark.asyncio
async def test_half_width_garment_vs_girth_body():
    """
    Reproduce the issue where a Half-Width garment (flat measurement) 
    is compared directly to a Girth body (circumference), leading to 
    extreme size recommendations (XXL) because the garment appears too small.
    """
    recommender = Recommender()
    
    # Garment Scale (Half-Width)
    # Target Ease for Chest is 6.0cm.
    # Body is 104cm. Ideal Garment Girth is 110cm.
    # Ideal Garment Half-Width is 55cm.
    
    garment_scale = {
        "units": ["cm", "inch"],
        "scale_cm": {
            "S": {"chest": 51.0}, # 102 (Tight)
            "M": {"chest": 55.0}, # 110 (Perfect, Slack 6)
            "L": {"chest": 59.0}, # 118 (Loose)
            "XL": {"chest": 63.0},
            "XXL": {"chest": 67.0}
        },
        "scale_in": {
            "S": {"chest": 20.0},
            "M": {"chest": 21.65}, # ~55cm
            "L": {"chest": 23.2},
            "XL": {"chest": 24.8},
            "XXL": {"chest": 26.4}
        }
    }
    
    # User Body (Girth)
    # Chest: 104cm
    body_cm = {"chest": 104.0}
    
    # 1. Test with CM
    result_cm = await recommender.recommend(
        body_measurements=body_cm,
        garment_scale=garment_scale,
        garment_category_id=3,
        user_unit="cm"
    )
    
    print(f"CM Recommendation: {result_cm['recommended_size']}")
    print(f"CM Details: {result_cm['match_details']}")
    
    # 2. Test with Inch
    body_in = {"chest": 40.9}
    result_in = await recommender.recommend(
        body_measurements=body_in,
        garment_scale=garment_scale,
        garment_category_id=3,
        user_unit="inch"
    )
    
    print(f"Inch Recommendation: {result_in['recommended_size']}")
    print(f"Inch Details: {result_in['match_details']}")

    assert result_cm['recommended_size'] == "M", f"Expected M, got {result_cm['recommended_size']}"
    assert result_in['recommended_size'] == "M", f"Expected M, got {result_in['recommended_size']}"
