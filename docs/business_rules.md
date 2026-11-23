# Business Rules

This document records implemented behavior and explicitly unresolved rules.

- Accept multiple Excel workbooks and use only the `RCA_Data` worksheet.
- Retain the 12 mandatory standardized columns and reject missing mandatory columns.
- Present potential spelling/mapping corrections for approval before applying them.
- Use the `Circle` column in `RCA_Data` as the authoritative Circle source.
- Consolidate records across circles and remove exact duplicates using all 12 standardized columns.
- Validate `Final Bucket` plus `Bucket - 2` as a pair and report mismatches without changing values.
- Filter by the selected reporting date, O&M Start = Yes, and Outage Min. > 0.
- Export a formatted `RCA_Data` worksheet. Circle summary sheets and standalone validation workbook sheets are not implemented.

## Circle source-of-truth

- The mandatory `Circle` column in `RCA_Data` is authoritative. If it is
  missing, the workbook fails schema validation.
- Do not require manual Circle selection during normal uploads, or use a
  manually selected Circle to overwrite or replace values from the worksheet.
- Flag blank Circle values in validation results; do not silently fill them.
- Preserve original Circle values during consolidation. Do not automatically
  rename or correct them.
- Do not assume an uploaded workbook contains only one Circle unless a
  separate business rule explicitly establishes that.

The pairwise bucket mapping remains provisional until the actual reference workbook is independently reopened and verified.
