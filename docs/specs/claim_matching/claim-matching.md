# Claim Matching Spec (Draft)

## Purpose
Define the inputs, outputs, and matching rules for comparing numeric claims extracted from a brief text source against slide OCR text. This spec focuses on behavior and expected results, not implementation.

## Inputs
1. **Brief text source**
   - Source formats: Markdown or Word.
   - Pre-processing: normalize to plain text (remove styling, preserve sentences and numeric tokens).
   - Claims are parsed from normalized text and assigned a `claim_id`.

2. **Slide OCR text**
   - Each slide provides:
     - `slide_id` (unique identifier for a slide)
     - `ocr_text` (normalized plain text from OCR)

## Outputs
For each claim, produce a structured result:
- `claim_id`
- `status`: one of
  - **matched** (evidence supports claim)
  - **mismatch** (evidence contradicts claim)
  - **not_found** (no numeric evidence located)
- `evidence_refs`: list of evidence items
  - Each item includes `slide_id` and a snippet or token reference
- `summary_counts`
  - total claims
  - matched count
  - mismatch count
  - not_found count

## Matching Logic
### Numeric-only claims
- A numeric-only claim is a claim that includes a number with optional unit (e.g., `45%`, `+2 pp`, `3.5`), but no other factual text that must be matched.
- The matching process searches slide OCR text for numeric tokens and unit markers that correspond to the claim.

### Unit handling
- **Percent (`%`) vs percentage points (`pp`)**
  - Treat `%` as a proportion value.
  - Treat `pp` as an absolute difference between two percentages.
  - `%` and `pp` are not equivalent and must be distinguished.

### Tolerance rules
- Default behavior is **exact match** for numeric-only claims unless a tolerance is explicitly configured.
- If tolerance is enabled, apply it symmetrically around the claim value.

## Examples
### 1) `%` vs `pp` normalization
**Claim**: “Increase of 2 pp”
- Parsed as: `value=2`, `unit=pp`
- **Match example**:
  - OCR: “Increase of 2 pp year-over-year” → **matched**
- **Mismatch example**:
  - OCR: “Increase of 2% year-over-year” → **mismatch** (unit differs)

**Claim**: “Conversion rate is 45%”
- Parsed as: `value=45`, `unit=%`
- **Match example**:
  - OCR: “Conversion rate: 45%” → **matched**
- **Mismatch example**:
  - OCR: “Conversion rate: 45 pp” → **mismatch** (unit differs)

### 2) Numeric-only claims with/without units
**Claim**: “7.5” (no unit)
- **Match example**:
  - OCR: “Average score 7.5” → **matched**
- **Mismatch example**:
  - OCR: “Average score 7.4” → **mismatch**

**Claim**: “7.5%”
- **Match example**:
  - OCR: “Average score 7.5%” → **matched**
- **Mismatch example**:
  - OCR: “Average score 7.5” → **mismatch** (unit missing)

### 3) Tolerance behavior
**Claim**: “10.0%” with tolerance **±0.1**
- **Match examples**:
  - OCR: “10.0%” → **matched**
  - OCR: “9.9%” → **matched**
  - OCR: “10.1%” → **matched**
- **Mismatch examples**:
  - OCR: “9.8%” → **mismatch**
  - OCR: “10.2%” → **mismatch**

**Claim**: “10.0%” with **exact match**
- **Match example**:
  - OCR: “10.0%” → **matched**
- **Mismatch examples**:
  - OCR: “9.9%” → **mismatch**
  - OCR: “10.1%” → **mismatch**
