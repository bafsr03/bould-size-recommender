"""
Regression test: Ensure 6'1" (185cm) user cannot get XS/S for hoodie
unless body measurements are extremely small and user explicitly selects tight fit.
Standalone version using unittest and mocking dependencies.
"""
import unittest
import sys
import asyncio
from unittest.mock import MagicMock, AsyncMock

# --- MOCK DEPENDENCIES START ---
# We mock these BEFORE importing app.services.recommender to avoid ImportError
# due to missing dependencies in the environment (pydantic, fastapi, etc.)

# Mock app.config
mock_config = MagicMock()
mock_config.settings.recommender_unit = "cm"
sys.modules["app.config"] = mock_config

# Mock app.services.llm
mock_llm_module = MagicMock()
mock_llm_class = MagicMock()
mock_llm_module.TailorLLM = mock_llm_class
sys.modules["app.services.llm"] = mock_llm_module

# Also need to ensure relative imports work if we run this as a script
# We'll just rely on the test runner setting PYTHONPATH or us adding it
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# --- MOCK DEPENDENCIES END ---

from app.services.recommender import Recommender

class TestTallUserXSBug(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.recommender = Recommender()
        # Mock LLM instance
        self.recommender.llm = MagicMock()
        # Async mock for generate_feedback
        # We can just use an AsyncMock here which is easier
        self.recommender.llm.generate_feedback = AsyncMock(return_value={"final": "mock", "preview": []})

    async def test_tall_user_cannot_get_xs_for_hoodie(self):
        """6'1" user should never get XS for hoodie with regular/relaxed fit"""
        
        # 6'1" = 185cm
        body_measurements = {
            "chest": 98.0,
            "waist": 85.0,
            "shoulder_width": 45.0,
            "sleeve_length": 62.0,
            "hips": 95.0,
        }

        # Hoodie size scale
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

        result = await self.recommender.recommend(
            body_measurements=body_measurements,
            garment_scale=garment_scale,
            garment_category_id=3,
            user_unit="cm",
            tone="regular",
            height_cm=185.0,
            debug=True,
        )

        self.assertNotIn(result["recommended_size"], ["XS", "S"],
                        f"6'1\" user got {result['recommended_size']} - should be at least M")
        
        self.assertIn(result["recommended_size"], ["L", "XL"],
                      f"Expected L or XL for 6'1\" user, got {result['recommended_size']}")
        
        self.assertGreater(result["confidence"], 0.5,
                          f"Confidence too low: {result['confidence']}")

    async def test_tall_user_with_incomplete_measurements(self):
        """Test case where body measurements are incomplete"""
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

        result = await self.recommender.recommend(
            body_measurements=body_measurements,
            garment_scale=garment_scale,
            garment_category_id=3,
            user_unit="cm",
            height_cm=185.0,
            debug=True,
        )

        self.assertNotIn(result["recommended_size"], ["XS", "S"],
                        f"Incomplete measurements led to {result['recommended_size']} - should penalize missing metrics")
        
        self.assertLess(result["confidence"], 0.8,
                       f"Confidence too high with missing metrics: {result['confidence']}")

    async def test_height_185cm_minimum_size_guardrail(self):
        """Test guardrail enforcement"""
        body_measurements = {
            "chest": 95.0,
            "waist": 82.0,
            "shoulder_width": 42.0,
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

        result = await self.recommender.recommend(
            body_measurements=body_measurements,
            garment_scale=garment_scale,
            garment_category_id=3,
            user_unit="cm",
            tone="regular",
            height_cm=185.0,
            debug=True,
        )

        self.assertIn(result["recommended_size"], ["L", "XL"],
                     f"185cm user should get at least L, got {result['recommended_size']}")

if __name__ == "__main__":
    unittest.main()
