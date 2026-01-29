"""
End-to-end integration test simulating full request through orchestrator.
Tests the 6'1" user XS bug scenario with fixed fixtures.
"""
import pytest
import sys
import json
from unittest.mock import MagicMock, AsyncMock, patch

# Mock LLM module before importing recommender to avoid segfault
mock_llm_module = MagicMock()
mock_llm_class = MagicMock()
mock_llm_module.TailorLLM = mock_llm_class
sys.modules['app.services.llm'] = mock_llm_module

from app.services.recommender import Recommender
from app.services.body_api import BodyApiClient
from app.services.garment_api import GarmentApiClient


@pytest.mark.asyncio
async def test_integration_tall_user_hoodie_recommendation():
    """
    Full integration test: 6'1" user requesting hoodie recommendation.
    Simulates the exact failure scenario.
    """
    # Mock LLM
    recommender = Recommender()
    recommender.llm = MagicMock()
    async def mock_feedback(*args, **kwargs):
        return {"final": "Based on your measurements, we recommend this size.", "preview": []}
    recommender.llm.generate_feedback.side_effect = mock_feedback

    # Fixed fixture: Body API response for 6'1" (185cm) user
    # This simulates what Body API would return
    body_measurements_from_api = {
        "chest": 98.0,
        "waist": 85.0,
        "shoulder_width": 45.0,
        "sleeve_length": 62.0,
        "hips": 95.0,
        "inseam": 83.0,
        "thigh": 58.0,
    }

    # Fixed fixture: Garment API response for hoodie
    # This simulates what Garment API would return
    garment_scale_from_api = {
        "units": ["cm", "inch"],
        "chart_type": "garment",
        "true_size": "M",
        "scale_cm": {
            "XS": {
                "chest": 88.0,
                "waist": 82.0,
                "shoulder_width": 38.0,
                "sleeve_length": 55.0,
            },
            "S": {
                "chest": 92.0,
                "waist": 86.0,
                "shoulder_width": 40.0,
                "sleeve_length": 57.0,
            },
            "M": {
                "chest": 96.0,
                "waist": 90.0,
                "shoulder_width": 42.0,
                "sleeve_length": 59.0,
            },
            "L": {
                "chest": 100.0,
                "waist": 94.0,
                "shoulder_width": 44.0,
                "sleeve_length": 61.0,
            },
            "XL": {
                "chest": 104.0,
                "waist": 98.0,
                "shoulder_width": 46.0,
                "sleeve_length": 63.0,
            },
            "XXL": {
                "chest": 108.0,
                "waist": 102.0,
                "shoulder_width": 48.0,
                "sleeve_length": 65.0,
            },
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

    # Simulate full recommendation flow
    result = await recommender.recommend(
        body_measurements=body_measurements_from_api,
        garment_scale=garment_scale_from_api,
        garment_category_id=3,  # Upper body (hoodie)
        user_unit="cm",
        height_cm=185.0,  # 6'1"
        tone="regular",
        debug=True,
    )

    # Assertions: Should NOT recommend XS or S
    assert result["recommended_size"] not in ["XS", "S"], \
        f"FAILED: 6'1\" user got {result['recommended_size']} - this is the bug!"
    
    # Should recommend L or XL (appropriate for tall person)
    assert result["recommended_size"] in ["L", "XL"], \
        f"Expected L or XL for 6'1\" user, got {result['recommended_size']}"
    
    # Confidence should be reasonable
    assert result["confidence"] > 0.5, \
        f"Confidence too low: {result['confidence']}"
    
    # Debug output should be present
    assert "debug" in result, "Debug output missing"
    assert result["debug"]["height_cm"] == 185.0, "Height not in debug"
    assert result["debug"]["guardrail_applied"] == "L", "Guardrail not applied"
    
    # Guardrail is applied (minimum L), but reason code only added if enforcement was needed
    # Since recommendation is already L/XL, guardrail doesn't need to enforce
    # So reason code may or may not be present - that's fine


@pytest.mark.asyncio
async def test_integration_incomplete_measurements_scenario():
    """
    Test the bug scenario: incomplete body measurements (missing shoulder/sleeve).
    This is what likely caused the original bug.
    """
    recommender = Recommender()
    recommender.llm = MagicMock()
    async def mock_feedback(*args, **kwargs):
        return {"final": "mock", "preview": []}
    recommender.llm.generate_feedback.side_effect = mock_feedback

    # Incomplete measurements - missing critical metrics
    incomplete_body = {
        "chest": 98.0,
        "waist": 85.0,
        # Missing: shoulder_width, sleeve_length (critical for upper body)
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
        body_measurements=incomplete_body,
        garment_scale=garment_scale,
        garment_category_id=3,
        user_unit="cm",
        height_cm=185.0,
        debug=True,
    )

    # Even with incomplete measurements, should not recommend XS
    # Missing metrics should be penalized
    assert result["recommended_size"] not in ["XS", "S"], \
        f"Incomplete measurements led to {result['recommended_size']} - missing metrics not penalized"
    
    # Confidence should be lower due to missing metrics
    assert result["confidence"] < 0.9, \
        f"Confidence too high with missing metrics: {result['confidence']}"
    
    # Debug should show missing metrics
    if "debug" in result:
        debug = result["debug"]
        # Check that missing metrics are tracked
        assert "per_size_scores" in debug, "Per-size scores missing from debug"


@pytest.mark.asyncio
async def test_integration_chart_type_validation():
    """Test that chart_type is properly validated"""
    recommender = Recommender()
    recommender.llm = MagicMock()
    async def mock_feedback(*args, **kwargs):
        return {"final": "mock", "preview": []}
    recommender.llm.generate_feedback.side_effect = mock_feedback

    body = {"chest": 100.0, "waist": 85.0, "shoulder_width": 45.0, "sleeve_length": 62.0}
    
    # Test with explicit chart_type
    garment_scale_with_type = {
        "units": ["cm", "inch"],
        "chart_type": "garment",
        "true_size": "M",
        "scale_cm": {
            "M": {"chest": 96.0, "waist": 90.0, "shoulder_width": 42.0, "sleeve_length": 59.0},
            "L": {"chest": 100.0, "waist": 94.0, "shoulder_width": 44.0, "sleeve_length": 61.0},
        },
    }
    
    result = await recommender.recommend(
        body_measurements=body,
        garment_scale=garment_scale_with_type,
        garment_category_id=3,
        user_unit="cm",
        debug=True,
    )
    
    # Should work with chart_type
    assert result["recommended_size"] in ["M", "L"]
    assert result["debug"]["chart_type"] == "garment"
    
    # Test with invalid chart_type
    garment_scale_invalid = {
        "units": ["cm", "inch"],
        "chart_type": "invalid_type",
        "true_size": "M",
        "scale_cm": {"M": {"chest": 96.0}},
    }
    
    with pytest.raises(ValueError, match="Invalid chart_type"):
        await recommender.recommend(
            body_measurements=body,
            garment_scale=garment_scale_invalid,
            garment_category_id=3,
            user_unit="cm",
        )
