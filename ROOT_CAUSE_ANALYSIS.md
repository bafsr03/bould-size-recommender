# Root Cause Analysis: 6'1" User Recommended XS for Hoodie

## Incident Summary
A user with height 6'1" (185 cm) received XS recommendation for a hoodie (category 3 - upper body), which is clearly incorrect.

## Root Causes Identified

### 1. **Missing Metrics Silently Skipped in Scoring** (CRITICAL)
**Location**: `app/services/recommender.py:66-67`

```python
if b is None or g is None:
    continue  # <-- BUG: Silently skips missing metrics
```

**Impact**: 
- If body measurements are incomplete (e.g., missing `shoulder_width`, `sleeve_length`), only available metrics are scored
- For hoodie (category 3), relevant metrics are: `["chest", "waist", "shoulder_width", "sleeve_length"]`
- If `shoulder_width` and `sleeve_length` are missing, only `chest` and `waist` are scored
- XS might score well on chest/waist alone, even though it's too small for a tall person

**Example Scenario**:
- Body: `{chest: 100, waist: 85}` (missing shoulder_width, sleeve_length)
- XS garment: `{chest: 92, waist: 90}` → scores well (chest +2cm, waist +5cm)
- L garment: `{chest: 104, waist: 108}` → scores worse (too loose)
- Result: XS wins despite being too small for 6'1" person

### 2. **No Height-Based Validation** (CRITICAL)
**Location**: `app/routers/recommend.py` and `app/services/recommender.py`

**Impact**:
- No validation that body measurements are reasonable for height
- A 6'1" (185cm) person should have minimum:
  - Chest: ~95-100cm (proportional to height)
  - Shoulder width: ~42-46cm
  - Sleeve length: ~60-65cm
- If Body API returns incorrect measurements or missing data, no sanity check

### 3. **No Chart Type Field** (HIGH)
**Location**: `Automatic-Garments-Size-Measurement-using-HRNet-and-Point-Cloud/api_app/pipeline.py:386-394`

**Impact**:
- Garment scales don't indicate if they're:
  - `garment`: Actual garment measurements (ease already included)
  - `body`: Body size chart (ease must be applied)
- Current code assumes all scales are garment measurements
- If a body chart is provided, ease is double-applied, causing wrong recommendations

### 4. **Naive Confidence Calculation** (MEDIUM)
**Location**: `app/services/recommender.py:241`

```python
confidence = max(0.0, 1.0 - (best_score / 100.0))
```

**Impact**:
- If best_score is 0 (all metrics missing or perfect match), confidence = 1.0
- Doesn't account for missing critical metrics
- Doesn't validate that recommendation makes sense

### 5. **No Minimum Size Guardrails** (HIGH)
**Location**: `app/services/recommender.py:recommend()`

**Impact**:
- No rules preventing obviously wrong sizes
- A 6'1" person should never get XS/S for regular fit unless explicitly requesting tight fit
- No validation that body exceeds largest available size

### 6. **Category Auto-Switching Can Be Wrong** (MEDIUM)
**Location**: `app/services/recommender.py:210-212`

**Impact**:
- Heuristic switches category if key overlap is better
- Might switch from upper (3) to lower (1) incorrectly
- Wrong category = wrong metrics = wrong scoring

## Files Responsible

1. **`app/services/recommender.py`**:
   - `_score_size()`: Missing metrics handling (line 66-67)
   - `recommend()`: No height validation, no guardrails, naive confidence (lines 106-270)

2. **`app/routers/recommend.py`**:
   - No validation of body measurements against height (lines 48-91)

3. **`Automatic-Garments-Size-Measurement-using-HRNet-and-Point-Cloud/api_app/pipeline.py`**:
   - Missing `chart_type` field in size scale JSON (line 386-394)

## Proof of Concept

For a 6'1" (185cm) user:
- Expected chest: ~96-100cm
- Expected shoulder: ~44-46cm
- If Body API returns incomplete data: `{chest: 92, waist: 80}` (missing shoulder, sleeve)
- XS hoodie: `{chest: 88, waist: 85}` → scores 4.0 (chest -4cm, waist +5cm)
- M hoodie: `{chest: 96, waist: 100}` → scores 6.0 (chest 0cm, waist +20cm)
- **Result: XS wins with confidence 0.96** ❌

## Fix Strategy

1. **Add missing metrics penalty**: Penalize sizes when critical metrics are missing
2. **Height-based validation**: Reject or warn on measurements that don't match height
3. **Add chart_type field**: Fail fast if missing, default to "garment" for legacy
4. **Add guardrails**: Minimum size rules based on height and body measurements
5. **Improve confidence**: Account for missing metrics and edge cases
6. **Add debug output**: Structured logging for all calculations
