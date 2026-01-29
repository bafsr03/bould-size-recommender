# Fixes Summary: 6'1" User XS Recommendation Bug

## Problem
A user with height 6'1" (185 cm) received XS recommendation for a hoodie, which is clearly incorrect.

## Root Causes Fixed

### 1. ✅ Missing Metrics Silently Skipped
**Fix**: Added penalty (50 points per missing metric, weighted) when critical metrics are missing.
- **File**: `app/services/recommender.py:59-98`
- **Impact**: Prevents sizes from scoring well when metrics are incomplete

### 2. ✅ No Height-Based Validation
**Fix**: Added height guardrails enforcing minimum sizes:
- ≥183cm (6'0"): Minimum L
- ≥190cm (6'3"): Minimum XL
- **File**: `app/services/recommender.py:32-42, 240-280`
- **Impact**: Tall users can no longer get XS/S unless explicitly requesting tight fit

### 3. ✅ No Chart Type Field
**Fix**: Added `chart_type` field to garment scales with validation:
- Default: "garment" (for legacy data)
- Valid values: "garment" or "body"
- Fails fast on invalid values
- **Files**: 
  - `app/services/recommender.py:125-135`
  - `Automatic-Garments-Size-Measurement-using-HRNet-and-Point-Cloud/api_app/pipeline.py:386-398`
- **Impact**: Prevents double-applying ease when body charts are used

### 4. ✅ Naive Confidence Calculation
**Fix**: Improved confidence calculation:
- Penalizes for missing critical metrics (20% per metric)
- Accounts for guardrail enforcement
- Adds reason codes for low confidence
- **File**: `app/services/recommender.py:290-320`
- **Impact**: Confidence scores now reflect data quality

### 5. ✅ No Debug Output
**Fix**: Added structured debug output (behind flag):
- Normalized units
- Chart type
- Body metrics used
- Per-size deltas and scores
- Reason codes
- Guardrail info
- **Files**: 
  - `app/services/recommender.py:350-375`
  - `app/routers/recommend.py:154-175`
- **Impact**: Enables debugging of recommendation issues

## Safety Rules Implemented

1. **Height Guardrails**: Enforce minimum sizes for tall users
2. **Missing Metrics Penalty**: Penalize sizes when critical metrics are missing
3. **Confidence Thresholds**: Warn or reject low-confidence recommendations
4. **Chart Type Validation**: Fail fast on invalid chart types

## Testing

### Regression Tests
- `tests/test_tall_user_xs_bug.py`: Ensures 6'1" user cannot get XS/S
- `tests/test_integration_tall_user.py`: Full integration test with fixtures

### Test Coverage
- ✅ Height-based guardrails
- ✅ Missing metrics handling
- ✅ Chart type validation
- ✅ Confidence calculation
- ✅ Debug output

## Usage

### Enable Debug Mode
Set environment variable:
```bash
DEBUG_RECOMMENDATIONS=1
```

### Height Guardrails
Height is automatically extracted from:
- `height` form parameter
- `height` field in `measurements_json`

Guardrails apply automatically when height ≥183cm.

### Chart Type
New garment scales include `chart_type`:
```json
{
  "chart_type": "garment",
  "scale_cm": {...},
  "scale_in": {...}
}
```

Legacy scales without `chart_type` default to "garment" (with warning in debug mode).

## Breaking Changes

**None** - All changes are backward compatible:
- Height parameter is optional
- Debug mode is opt-in
- Chart type defaults for legacy data
- Guardrails only apply when height is provided

## Performance Impact

- Minimal: Guardrail checks are O(1)
- Missing metrics penalty adds small overhead
- Debug output only when flag is set

## Next Steps

1. Monitor production for guardrail enforcement rate
2. Collect user feedback on recommendation accuracy
3. Tune guardrail thresholds based on data
4. Add more sophisticated BMI-based guardrails (future)
