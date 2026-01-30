"""
End-to-end integration test simulating full request through orchestrator.
Standalone version using unittest and mocking.
"""
import unittest
import sys
import asyncio
import json
from unittest.mock import MagicMock, AsyncMock

# --- MOCK DEPENDENCIES START ---
mock_config = MagicMock()
mock_config.settings.recommender_unit = "cm"
sys.modules["app.config"] = mock_config

mock_llm_module = MagicMock()
mock_llm_class = MagicMock()
mock_llm_module.TailorLLM = mock_llm_class
sys.modules["app.services.llm"] = mock_llm_module

# Mock Body API and Garment API as they might need dependencies too
sys.modules["app.services.body_api"] = MagicMock()
sys.modules["app.services.garment_api"] = MagicMock()

import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
# --- MOCK DEPENDENCIES END ---

from app.services.recommender import Recommender

class TestIntegrationTallUser(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.recommender = Recommender()
        self.recommender.llm = MagicMock()
        self.recommender.llm.generate_feedback = AsyncMock(return_value={"final": "mock", "preview": []})

    async def test_integration_tall_user_hoodie_recommendation(self):
        body_measurements_from_api = {
            "chest": 98.0, "waist": 85.0, "shoulder_width": 45.0, 
            "sleeve_length": 62.0, "hips": 95.0, "inseam": 83.0, "thigh": 58.0,
        }

        garment_scale_from_api = {
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
            body_measurements=body_measurements_from_api,
            garment_scale=garment_scale_from_api,
            garment_category_id=3,
            user_unit="cm",
            height_cm=185.0,
            tone="regular",
            debug=True,
        )

        self.assertNotIn(result["recommended_size"], ["XS", "S"], "FAILED: 6'1\" user got XS/S")
        self.assertIn(result["recommended_size"], ["L", "XL"], "Expected L or XL")
        self.assertGreater(result["confidence"], 0.5)
        self.assertEqual(result["debug"]["height_cm"], 185.0)
        self.assertEqual(result["debug"]["guardrail_applied"], "L")

    async def test_integration_chart_type_validation(self):
        body = {"chest": 100.0, "waist": 85.0, "shoulder_width": 45.0, "sleeve_length": 62.0}
        
        garment_scale_with_type = {
            "units": ["cm", "inch"],
            "chart_type": "garment",
            "true_size": "M",
            "scale_cm": {
                "M": {"chest": 96.0, "waist": 90.0, "shoulder_width": 42.0, "sleeve_length": 59.0},
                "L": {"chest": 100.0, "waist": 94.0, "shoulder_width": 44.0, "sleeve_length": 61.0},
            },
        }
        
        result = await self.recommender.recommend(
            body_measurements=body,
            garment_scale=garment_scale_with_type,
            garment_category_id=3,
            user_unit="cm",
            debug=True,
        )
        
        self.assertIn(result["recommended_size"], ["M", "L"])
        self.assertEqual(result["debug"]["chart_type"], "garment")
        
        garment_scale_invalid = {
            "units": ["cm", "inch"],
            "chart_type": "invalid_type",
            "true_size": "M",
            "scale_cm": {"M": {"chest": 96.0}},
        }
        
        with self.assertRaisesRegex(ValueError, "Invalid chart_type"):
            await self.recommender.recommend(
                body_measurements=body,
                garment_scale=garment_scale_invalid,
                garment_category_id=3,
                user_unit="cm",
            )

if __name__ == "__main__":
    unittest.main()
