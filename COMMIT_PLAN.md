# Commit Plan: Fix 6'1" User XS Recommendation Bug

## Summary

Fixes critical bug where tall users (6'1" / 185cm) could receive XS recommendations for hoodies. Implements guardrails, missing metrics handling, chart_type validation, and debug output.

## Changes by Commit

### Commit 1: Root Cause Analysis and Tests

**Files:**

- `ROOT_CAUSE_ANALYSIS.md` - Detailed analysis of the bug
- `tests/test_tall_user_xs_bug.py` - Regression tests
- `tests/test_integration_tall_user.py` - End-to-end integration tests

**What it does:**

- Documents the root causes (missing metrics, no height validation, etc.)
- Creates reproducible test cases that fail before the fix
- Tests guardrail behavior

### Commit 2: Fix Scoring Logic - Penalize Missing Metrics

**Files:**

- `app/services/recommender.py` - `_score_size()` function

**What it does:**

- Changes `_score_size()` to return debug info
- Adds penalty for missing critical metrics (50 points per missing metric, weighted)
- Prevents sizes from scoring well when metrics are missing

**Key change:**

```python
# Before: Missing metrics silently skipped
if b is None or g is None:
    continue

# After: Missing metrics penalized
missing_penalty += 50.0 * weight
```

### Commit 3: Add Height-Based Guardrails

**Files:**

- `app/services/recommender.py` - `recommend()` method
- Constants: `HEIGHT_GUARDRAILS`

**What it does:**

- Enforces minimum size (L) for users ≥183cm (6'0")
- Enforces minimum size (XL) for users ≥190cm (6'3")
- Validates body measurements against height
- Allows override only for explicit "tight" fit preference

**Key change:**

```python
if height_cm >= 183:
    guardrail_min_size = "L"
    # Enforce unless tone is "tight"
```

### Commit 4: Add Chart Type Validation

**Files:**

- `app/services/recommender.py` - `recommend()` method
- `Automatic-Garments-Size-Measurement-using-HRNet-and-Point-Cloud/api_app/pipeline.py` - Size scale generation

**What it does:**

- Adds `chart_type` field to garment scales (default: "garment")
- Validates chart_type is "garment" or "body"
- Fails fast on invalid chart_type
- Legacy support: defaults to "garment" if missing (with warning)

**Key change:**

```python
chart_type = garment_scale.get("chart_type", "garment")  # Default for legacy
if chart_type not in ("garment", "body"):
    raise ValueError(f"Invalid chart_type: {chart_type}")
```

### Commit 5: Improve Confidence Calculation

**Files:**

- `app/services/recommender.py` - `recommend()` method
- Constants: `MIN_CONFIDENCE_THRESHOLD`, `WARNING_CONFIDENCE_THRESHOLD`

**What it does:**

- Penalizes confidence for missing critical metrics
- Adds reason codes for low confidence
- Reduces confidence when guardrails are enforced

**Key change:**

```python
# Penalize for missing critical metrics
if missing_critical:
    base_confidence *= (1.0 - 0.2 * len(missing_critical))
```

### Commit 6: Add Structured Debug Output

**Files:**

- `app/services/recommender.py` - `recommend()` method
- `app/routers/recommend.py` - Router updates
- `app/schemas/recommend.py` - Response schema

**What it does:**

- Adds `debug` parameter to `recommend()`
- Returns structured debug info when `debug=True`:
  - Normalized units
  - Chart type
  - Body metrics used
  - Per-size deltas and scores
  - Reason codes
  - Guardrail info
- Controlled by `DEBUG_RECOMMENDATIONS` env var

**Key change:**

```python
if debug:
    result["debug"] = {
        "normalized_units": {...},
        "per_size_scores": {...},
        "reason_codes": [...],
        ...
    }
```

### Commit 7: Update Router to Pass Height and Debug

**Files:**

- `app/routers/recommend.py`

**What it does:**

- Extracts height from request (Form or measurements_json)
- Passes height to recommender for guardrails
- Enables debug mode via `DEBUG_RECOMMENDATIONS` env var
- Merges debug output into response

## Testing Strategy

1. **Unit Tests**: `test_tall_user_xs_bug.py`
   - Tests guardrail enforcement
   - Tests missing metrics penalty
   - Tests height-based validation

2. **Integration Tests**: `test_integration_tall_user.py`
   - Full flow with fixed fixtures
   - Tests incomplete measurements scenario
   - Tests chart_type validation

3. **Manual Testing**:
   - Test with height 185cm, regular fit → should get L or XL
   - Test with height 185cm, tight fit → can get smaller sizes
   - Test with incomplete measurements → should penalize
   - Test with debug flag → should see structured output

## Rollout Plan

1. **Phase 1**: Deploy with guardrails disabled (feature flag)
   - Monitor for any regressions
   - Verify tests pass

2. **Phase 2**: Enable guardrails for new requests
   - Monitor recommendation quality
   - Check debug logs for reason codes

3. **Phase 3**: Full rollout
   - All requests use guardrails
   - Monitor for edge cases

## Rollback Plan

- Guardrails can be disabled by not passing `height_cm`
- Missing metrics penalty can be reduced by adjusting constant
- Chart_type validation can be made optional

## Metrics to Monitor

- Recommendation accuracy (user feedback)
- Confidence scores distribution
- Guardrail enforcement rate
- Missing metrics frequency
- Debug log volume
