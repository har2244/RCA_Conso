# Business Rules

This document records agreed behaviour. If code differs, report the discrepancy rather than silently changing the rule.

## Input workbooks
- Process only worksheet named exactly `RCA_Data`; ignore other sheets.
- Never modify uploaded source workbooks; operate on in-memory copies.
- Detect headers within the first five Excel rows.
- If no reliable header is found in those rows, flag the workbook.
- If multiple header candidates are ambiguous, require review.
- Extra columns are excluded from standardized output.

## Standard output columns (fixed order)
1. Date
2. Project
3. Circle
4. Site ID
5. Site Name
6. OA
7. BA
8. O&M Start (Yes/No)
9. Outage Min.
10. Final Bucket
11. Bucket - 2
12. RCA

Missing mandatory columns must be flagged; do not silently consolidate incomplete schema.

## Column mapping
- Exact/safe normalized matches may be applied according to current implementation.
- Fuzzy/suggested header mappings require explicit approval.
- Ambiguous mappings must not be silently applied.

## Project identity
Known app-supported Project identifiers: `LWE` and `4G Saturation`.
- Existing nonblank Project values are preserved.
- Missing Project values may require explicit assignment.
- Latest reported implemented rule: if Circle contains a recognizable `4G Satu` / `4G Saturation` variant (case, spacing, or hyphen tolerant), fill only a missing Project cell with `4G Saturation`.
- Do not overwrite existing nonblank Project values.
- Unrelated or missing Circle values remain on the manual-resolution path.
- Apply changes to in-memory copies and revalidate.
- Other unsupported/mixed Project values remain unresolved unless explicitly approved.

## Reporting date and filters
- User selects reporting date using a date picker (Option A).
- Date picker appears only after schema and Project validation pass.
- Selection is required; service rejects consolidation without a date.
- Last reported sequential filter order:
  1. Date equals selected reporting calendar date.
  2. O&M Start equals Yes (trimmed, case-insensitive).
  3. Numeric Outage Min. > 0.
- Reports should show per-file and batch stage counts/exclusions and invalid/blank counts.
- Standalone runner requires `--reporting-date YYYY-MM-DD`.

## Duplicates
- Exact duplicate rows across all 12 standardized columns are duplicates.
- Keep first occurrence, remove subsequent exact duplicates, report count.
- No separate cross-circle rule was agreed. Since Circle is a standard column, rows differing in Circle are not exact duplicates.

## Bucket validation — implemented; reference workbook not re-verified
- Bucket validation compares `Final Bucket` and `Bucket - 2` as a pair using trimmed, case-insensitive values.
- Missing, invalid, and mismatched values are reported.
- Original DataFrame values are preserved; bucket values are never auto-corrected.
- Findings include source workbook, Excel row number, both values, and reason.
- The Streamlit validation report shows per-file and batch valid/invalid counts.
- Current behavior is reporting only: bucket findings do not remove records or block consolidation.
- The mapping coded in `src/rca_consolidator/validation/bucket_validator.py` remains based on the provisional transcription. It has not been verified by reopening `Final Buckets & Sub Bucket bucketization.xlsx` because that reference workbook is not available in the workspace.

## Excel output formatting — implemented; master comparison pending
- Export requires exactly the 12 mandatory columns in canonical order.
- `RCA_Data` has a frozen header, filterable Excel Table, exact 12-column order, border styling, banded fills, configured widths, and text/number/date formats.
- Date displays use `dd-mmm-yyyy`, Site ID remains text, and Outage Min. becomes numeric when possible.
- Formatting operates on an export copy and does not alter the input DataFrame or uploaded source workbook.
- The coded colors and widths are implementation constants, not confirmed pixel-perfect matches from the November master workbook.

## Summary sheets
The implemented workbook export contains only `RCA_Data`. `CircleFocused`, `RCA Summary`, and standalone workbook validation report sheets are not implemented.
