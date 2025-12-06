import asyncio
import sys
import os
import json

# Add app to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.services.recommender import Recommender
from unittest.mock import MagicMock

async def reproduce_inch():
    # Mock LLM
    recommender = Recommender()
    recommender.llm = MagicMock()
    async def mock_feedback(*args, **kwargs):
        return {"final": "mock", "preview": []}
    recommender.llm.generate_feedback.side_effect = mock_feedback

    # User measurements converted to inches (approx)
    # Chest: 100.3 / 2.54 = 39.49
    # Waist: 86.82 / 2.54 = 34.18
    # Hips: 97.27 / 2.54 = 38.29
    # Shoulder: 46.18 / 2.54 = 18.18
    body_in = {
        'height': 68.9, # 175cm
        'waist': 34.18,
        'belly': 31.71,
        'chest': 39.49,
        'wrist': 6.11,
        'neck': 14.13,
        'arm_length': 22.05,
        'thigh': 20.80,
        'shoulder_width': 18.18,
        'hips': 38.29,
        'ankle': 8.19
    }

    # Garment Scale with both CM and Inch (simulating V2)
    scale_cm = {
        'XS': {'neck': 19.68, 'shoulder_width': 37.42, 'chest': 92.66, 'waist': 100.02, 'hem': 97.58, 'sleeve_length': 13.58, 'sleeve': 17.1, 'front_length': 66.61},
        'S': {'neck': 19.68, 'shoulder_width': 41.42, 'chest': 96.66, 'waist': 104.02, 'hem': 101.58, 'sleeve_length': 15.58, 'sleeve': 17.1, 'front_length': 68.61},
        'M': {'neck': 19.68, 'shoulder_width': 45.42, 'chest': 100.66, 'waist': 108.02, 'hem': 105.58, 'sleeve_length': 17.58, 'sleeve': 17.1, 'front_length': 70.61},
        'L': {'neck': 19.68, 'shoulder_width': 49.42, 'chest': 104.66, 'waist': 112.02, 'hem': 109.58, 'sleeve_length': 19.58, 'sleeve': 17.1, 'front_length': 72.61},
        'XL': {'neck': 19.68, 'shoulder_width': 53.42, 'chest': 108.66, 'waist': 116.02, 'hem': 113.58, 'sleeve_length': 21.58, 'sleeve': 17.1, 'front_length': 74.61},
        'XXL': {'neck': 19.68, 'shoulder_width': 57.42, 'chest': 112.66, 'waist': 120.02, 'hem': 117.58, 'sleeve_length': 23.58, 'sleeve': 17.1, 'front_length': 76.61}
    }
    
    # Generate Inch scale
    scale_in = {}
    for size, metrics in scale_cm.items():
        scale_in[size] = {k: v / 2.54 for k, v in metrics.items()}

    garment_scale = {
        "units": ["cm", "inch"],
        "scale_cm": scale_cm,
        "scale_in": scale_in
    }

    # Test with Category ID 1 (Pants) + Unit INCHES (plural) - Hypothesis for failure
    print("--- Testing with Category ID 1 (Pants) + Unit INCHES (plural) ---")
    result = await recommender.recommend(
        body_measurements=body_in,
        garment_scale=garment_scale,
        garment_category_id=1,
        user_unit="inches"
    )
    print(f"Recommended Size: {result['recommended_size']}")
    print(f"Confidence: {result['confidence']}")
    print(f"Details: {result['match_details']}")

if __name__ == "__main__":
    asyncio.run(reproduce_inch())
