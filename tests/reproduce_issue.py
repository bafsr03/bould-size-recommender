import asyncio
import sys
import os

# Add app to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.services.recommender import Recommender
from unittest.mock import MagicMock

async def reproduce():
    # Mock LLM
    recommender = Recommender()
    recommender.llm = MagicMock()
    async def mock_feedback(*args, **kwargs):
        return {"final": "mock", "preview": []}
    recommender.llm.generate_feedback.side_effect = mock_feedback

    body = {
        'height': 175.0, 'waist': 86.82, 'belly': 80.54, 'chest': 100.3, 
        'wrist': 15.53, 'neck': 35.89, 'arm_length': 56.02, 'thigh': 52.84, 
        'shoulder_width': 46.18, 'hips': 97.27, 'ankle': 20.8
    }

    garment_scale = {
        "units": ["cm"],
        "scale_cm": {
            'XS': {'neck': 19.68, 'shoulder_width': 37.42, 'chest': 92.66, 'waist': 100.02, 'hem': 97.58, 'sleeve_length': 13.58, 'sleeve': 17.1, 'front_length': 66.61},
            'S': {'neck': 19.68, 'shoulder_width': 41.42, 'chest': 96.66, 'waist': 104.02, 'hem': 101.58, 'sleeve_length': 15.58, 'sleeve': 17.1, 'front_length': 68.61},
            'M': {'neck': 19.68, 'shoulder_width': 45.42, 'chest': 100.66, 'waist': 108.02, 'hem': 105.58, 'sleeve_length': 17.58, 'sleeve': 17.1, 'front_length': 70.61},
            'L': {'neck': 19.68, 'shoulder_width': 49.42, 'chest': 104.66, 'waist': 112.02, 'hem': 109.58, 'sleeve_length': 19.58, 'sleeve': 17.1, 'front_length': 72.61},
            'XL': {'neck': 19.68, 'shoulder_width': 53.42, 'chest': 108.66, 'waist': 116.02, 'hem': 113.58, 'sleeve_length': 21.58, 'sleeve': 17.1, 'front_length': 74.61},
            'XXL': {'neck': 19.68, 'shoulder_width': 57.42, 'chest': 112.66, 'waist': 120.02, 'hem': 117.58, 'sleeve_length': 23.58, 'sleeve': 17.1, 'front_length': 76.61}
        }
    }

    # Try with category_id=1 (Pants) - Hypothesis for why XS is picked
    print("--- Testing with Category ID 1 (Pants) ---")
    result = await recommender.recommend(
        body_measurements=body,
        garment_scale=garment_scale,
        garment_category_id=1,
        user_unit="cm"
    )
    print(f"Recommended Size: {result['recommended_size']}")
    print(f"Confidence: {result['confidence']}")
    print(f"Details: {result['match_details']}")

if __name__ == "__main__":
    asyncio.run(reproduce())
