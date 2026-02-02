import sys
import unittest
from unittest.mock import MagicMock, AsyncMock

# MOCK DEPENDENCIES BEFORE IMPORT
# We need to mock app.config and app.services.llm to avoid pydantic/other dep issues
mock_config = MagicMock()
mock_config.settings.recommender_unit = "cm"
sys.modules["app.config"] = mock_config

mock_llm = MagicMock()
sys.modules["app.services.llm"] = mock_llm

# Now we can import
from app.services.recommender import Recommender, get_height_based_size_range

class TestHeightRanges(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.recommender = Recommender()
        # Ensure LLM is mocked on the instance too
        self.recommender.llm = MagicMock()
        self.recommender.llm.generate_feedback = AsyncMock(return_value={"final": "mock", "preview": []})

    def test_height_function_check(self):
        # 163cm (<165) -> XS, S
        self.assertEqual(get_height_based_size_range(163), ("XS", "S"))
        # 168cm (<170) -> S, L
        self.assertEqual(get_height_based_size_range(168), ("S", "L"))
        # 170cm (5'7") -> M, L
        self.assertEqual(get_height_based_size_range(170), ("M", "L"))
        # 175cm -> M, L
        self.assertEqual(get_height_based_size_range(175), ("M", "L"))
        # 185cm (6'1") -> L, XL
        self.assertEqual(get_height_based_size_range(185), ("L", "XL"))

    async def test_recommender_strict_range_enforcement(self):
        # Setup common data
        garment_scale = {
            "chart_type": "garment",
            "unit": "cm",
            "scale_cm": {
                "XS": {"chest": 90, "waist": 80, "hips": 90}, 
                "S": {"chest": 95, "waist": 85, "hips": 95},
                "M": {"chest": 100, "waist": 90, "hips": 100},
                "L": {"chest": 105, "waist": 95, "hips": 105},
                "XL": {"chest": 110, "waist": 100, "hips": 110}
            }
        }
        
        # User is 5'7" (170cm), Chest 90 (Perfect XS/S fit)
        # But Strict Range for 170cm is M-L.
        body = {"chest": 90, "waist": 80, "hips": 90}
        
        # We need to ensure we run this inside an event loop if Recommender uses it,
        # but Recommender is mostly sync except for llm call which we mocked?
        # Recommender.recommend is async def.
        
        result = await self.recommender.recommend(
            body_measurements=body,
            garment_scale=garment_scale,
            garment_category_id=3,
            height_cm=170.18, # 5'7"
            debug=True
        )
        
        print(f"\nDEBUG OUTPUT for 5'7 test:\n{result.get('debug')}")
        
        # Should be M because S(95) and XS(90) are excluded by range M-L
        # Valid sizes: M, L.
        # Chest 90. M is 100. Diff 10.
        # S is 95. Diff 5. XS is 90. Diff 0.
        # But S and XS are NOT in consideration.
        # So it should pick M.
        self.assertEqual(result["recommended_size"], "M")
        
    async def test_tall_user_6_1_strict(self):
        # 6'1" (185cm) -> L - XL range.
        garment_scale = {
            "chart_type": "garment",
            "unit": "cm",
            "scale_cm": {
                "M": {"chest": 100, "waist": 90, "hips": 100},
                "L": {"chest": 105, "waist": 95, "hips": 105},
                "XL": {"chest": 110, "waist": 100, "hips": 110}
            }
        }
        
        # Body fits M perfectly (100)
        body = {"chest": 100, "waist": 90, "hips": 100}
        
        result = await self.recommender.recommend(
            body_measurements=body,
            garment_scale=garment_scale,
            garment_category_id=3,
            height_cm=185.4, # 6'1"
            debug=True
        )
        
        # Should be L because M is out of range (L-XL)
        self.assertEqual(result["recommended_size"], "L")

if __name__ == '__main__':
    unittest.main()
