import pytest
from app.services.recommender import _normalize_scale

def test_normalize_cm_half_width():
    """
    User Scenario:
    Input: CM, but Chest is ~44 (Half-Width), Shoulder is ~40 (CM).
    Old Logic: Saw Chest 44 < 90 -> Assumed Inches -> Chest 112cm (Huge).
    New Logic: See Shoulder 40 -> Assumes CM. See Chest 44 < 70 -> Assumes Half-Width -> Chest 88cm.
    """
    scale = {
        "unit": "cm",
        "scale": {
            "XS": {
                "chest": 44.0, # 88cm girth
                "shoulder_to_shoulder": 40.0, # 40cm
                "waist": 42.0 # 84cm girth
            }
        }
    }
    norm = _normalize_scale(scale)
    
    # Should be CM (no conversion factor) but doubled for chest/waist
    assert abs(norm["XS"]["chest"] - 88.0) < 0.1
    assert abs(norm["XS"]["waist"] - 84.0) < 0.1
    assert abs(norm["XS"]["shoulder_width"] - 40.0) < 0.1

def test_normalize_inches_explicit():
    """
    Standard Inches: Chest 40in, Shoulder 18in.
    """
    scale = {
        "unit": "inch",
        "scale": {
            "M": {
                "chest": 40.0, # 101.6cm
                "shoulder_width": 18.0 # 45.72cm
            }
        }
    }
    norm = _normalize_scale(scale)
    
    assert abs(norm["M"]["chest"] - 101.6) < 0.1
    assert abs(norm["M"]["shoulder_width"] - 45.72) < 0.1

def test_normalize_cm_girth_explicit():
    """
    Standard CM Girth: Chest 100cm, Shoulder 45cm.
    """
    scale = {
        "unit": "cm",
        "scale": {
            "M": {
                "chest": 100.0,
                "shoulder_width": 45.0
            }
        }
    }
    norm = _normalize_scale(scale)
    
    assert abs(norm["M"]["chest"] - 100.0) < 0.1
    assert abs(norm["M"]["shoulder_width"] - 45.0) < 0.1

def test_normalize_ambiguous_inches():
    """
    Ambiguous: Chest 40, No Shoulder. Declared CM.
    Should probably default to Half-Width CM (80cm) or Inch (101cm).
    Current logic: Default CM -> Half-Width -> 80cm.
    """
    scale = {
        "unit": "cm",
        "scale": {
            "M": {"chest": 40.0}
        }
    }
    norm = _normalize_scale(scale)
    
    # 40 * 2 = 80.
    assert abs(norm["M"]["chest"] - 80.0) < 0.1
