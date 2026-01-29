"""
Regression test: Ensure 6'1" (185cm) user cannot get XS/S for hoodie
unless body measurements are extremely small and user explicitly selects tight fit.
"""
import pytest
import sys
from unittest.mock import MagicMock, patch

# Mock LLM before importing recommender to avoid segfault
sys.modules['app.services.llm'] = MagicMock()

from app.services.recommender import Recommender


@pytest.mark.asyncio
async def test_tall_user_cannot_get_xs_for_hoodie():
    """6'1" user should never get XS for hoodie with regular/relaxed fit"""
    recommender = Recommender()
    recommender.llm = MagicMock()
    async def mock_feedback(*args, **kwargs):
        return {"final": "mock", "preview": []}
    recommender.llm.generate_feedback.side_effect = mock_feedback

    # 6'1" = 185cm - typical measurements for tall person
    body_measurements = {
        "chest": 98.0,  # Proportional to height
        "waist": 85.0,
        "shoulder_width": 45.0,  # Tall person has wider shoulders
        "sleeve_length": 62.0,  # Long arms
        "hips": 95.0,
    }

    # Hoodie size scale (category 3 = upper body)
    garment_scale = {
        "units": ["cm", "inch"],
        "chart_type": "garment",  # Garment measurements with ease
        "true_size": "M",
        "scale_cm": {
            "XS": {"chest": 88.0, "waist": 82.0, "shoulder_width": 38.0, "sleeve_length": 55.0},
            "S": {"chest": 92.0, "waist": 86.0, "shoulder_width": 40.0, "sleeve_length": 57.0},
            "M": {"chest": 96.0, "waist": 90.0, "shoulder_width": 42.0, "sleeve_length": 59.0},
            "L": {"chest": 100.0, "waist": 94.0, "shoulder_width": 44.0, "sleeve_length": 61.0},
            "XL": {"chest": 104.0, "waist": 98.0, "shoulder_width": 46.0, "sleeve_length": 63.0},
            "XXL": {"chest": 108.0, "waist": 102.0, "shoulder_width": 48.0, "sleeve_length": 65.0},
        },
        "scale_in": {
            "XS": {"chest": 34.6, "waist": 32.3, "shoulder_width": 15.0, "sleeve_length": 21.7},
            "S": {"chest": 36.2, "waist": 33.9, "shoulder_width": 15.7, "sleeve_length": 22.4},
            "M": {"chest": 37.8, "waist": 35.4, "shoulder_width": 16.5, "sleeve_length": 23.2},
            "L": {"chest": 39.4, "waist": 37.0, "shoulder_width": 17.3, "sleeve_length": 24.0},
            "XL": {"chest": 40.9, "waist": 38.6, "shoulder_width": 18.1, "sleeve_length": 24.8},
            "XXL": {"chest": 42.5, "waist": 40.2, "shoulder_width": 18.9, "sleeve_length": 25.6},
        },
    }

    result = await recommender.recommend(
        body_measurements=body_measurements,
        garment_scale=garment_scale,
        garment_category_id=3,  # Upper body (hoodie)
        user_unit="cm",
        tone="regular",  # Regular fit, not tight
        height_cm=185.0,  # 6'1"
        debug=True,
    )

    # Should NOT recommend XS or S for tall user with regular fit
    assert result["recommended_size"] not in ["XS", "S"], \
        f"6'1\" user got {result['recommended_size']} - should be at least M"
    
    # Should recommend L or XL (best fit for tall person)
    assert result["recommended_size"] in ["L", "XL"], \
        f"Expected L or XL for 6'1\" user, got {result['recommended_size']}"
    
    # Confidence should be reasonable
    assert result["confidence"] > 0.5, \
        f"Confidence too low: {result['confidence']}"


@pytest.mark.asyncio
async def test_tall_user_with_incomplete_measurements():
    """Test case where body measurements are incomplete (missing shoulder/sleeve)"""
    recommender = Recommender()
    recommender.llm = MagicMock()
    async def mock_feedback(*args, **kwargs):
        return {"final": "mock", "preview": []}
    recommender.llm.generate_feedback.side_effect = mock_feedback

    # Incomplete measurements - missing shoulder_width and sleeve_length
    # This is the bug scenario: only chest/waist available
    body_measurements = {
        "chest": 98.0,
        "waist": 85.0,
        # Missing: shoulder_width, sleeve_length
    }

    garment_scale = {
        "units": ["cm", "inch"],
        "chart_type": "garment",
        "true_size": "M",
        "scale_cm": {
            "XS": {"chest": 88.0, "waist": 82.0, "shoulder_width": 38.0, "sleeve_length": 55.0},
            "S": {"chest": 92.0, "waist": 86.0, "shoulder_width": 40.0, "sleeve_length": 57.0},
            "M": {"chest": 96.0, "waist": 90.0, "shoulder_width": 42.0, "sleeve_length": 59.0},
            "L": {"chest": 100.0, "waist": 94.0, "shoulder_width": 44.0, "sleeve_length": 61.0},
            "XL": {"chest": 104.0, "waist": 98.0, "shoulder_width": 46.0, "sleeve_length": 63.0},
        },
    }

    result = await recommender.recommend(
        body_measurements=body_measurements,
        garment_scale=garment_scale,
        garment_category_id=3,
        user_unit="cm",
        height_cm=185.0,  # 6'1"
        debug=True,
    )

    # Even with incomplete measurements, should not recommend XS
    # The system should penalize missing metrics
    assert result["recommended_size"] not in ["XS", "S"], \
        f"Incomplete measurements led to {result['recommended_size']} - should penalize missing metrics"
    
    # Confidence should be lower due to missing metrics
    assert result["confidence"] < 0.8, \
        f"Confidence too high with missing metrics: {result['confidence']}"


@pytest.mark.asyncio
async def test_height_185cm_minimum_size_guardrail():
    """Test that height-based guardrail prevents XS/S for 185cm user"""
    recommender = Recommender()
    recommender.llm = MagicMock()
    async def mock_feedback(*args, **kwargs):
        return {"final": "mock", "preview": []}
    recommender.llm.generate_feedback.side_effect = mock_feedback

    # Simulate 185cm user with measurements
    # Height 185cm should have minimum chest ~95cm, shoulder ~42cm
    body_measurements = {
        "chest": 95.0,  # Minimum for 185cm
        "waist": 82.0,
        "shoulder_width": 42.0,  # Minimum for 185cm
        "sleeve_length": 60.0,
    }

    garment_scale = {
        "units": ["cm", "inch"],
        "chart_type": "garment",
        "true_size": "M",
        "scale_cm": {
            "XS": {"chest": 85.0, "waist": 78.0, "shoulder_width": 36.0, "sleeve_length": 53.0},
            "S": {"chest": 89.0, "waist": 82.0, "shoulder_width": 38.0, "sleeve_length": 55.0},
            "M": {"chest": 93.0, "waist": 86.0, "shoulder_width": 40.0, "sleeve_length": 57.0},
            "L": {"chest": 97.0, "waist": 90.0, "shoulder_width": 42.0, "sleeve_length": 59.0},
            "XL": {"chest": 101.0, "waist": 94.0, "shoulder_width": 44.0, "sleeve_length": 61.0},
        },
    }

    result = await recommender.recommend(
        body_measurements=body_measurements,
        garment_scale=garment_scale,
        garment_category_id=3,
        user_unit="cm",
        tone="regular",
        height_cm=185.0,  # 6'1"
        debug=True,
    )

    # Height guardrail should enforce minimum L for 185cm
    assert result["recommended_size"] in ["L", "XL"], \
        f"185cm user should get at least L, got {result['recommended_size']}"
