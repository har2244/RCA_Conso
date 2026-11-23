# Project Status

Last verified: 23 November 2026.

## Implemented and verified
- The Streamlit app prepares uploads, reads only `RCA_Data`, detects headers in the first five rows, validates mapped schemas, applies approved Project corrections, requires a reporting date, filters records, and removes exact duplicates.
- `Final Bucket` and `Bucket - 2` pair validation is implemented in `src/rca_consolidator/validation/bucket_validator.py`.
- Bucket findings are displayed in the Streamlit validation report with source filename, Excel row number, both values, and reasons.
- Bucket mismatches are findings rather than consolidation blockers; the app does not remove or correct mismatched records.
- Consolidated data can be downloaded as a formatted `RCA_Data` workbook through `src/rca_consolidator/export/excel_writer.py`.
- The export preserves the 12-column schema order, converts dates to Excel dates, preserves Site ID text, converts outage values to numbers, and applies a frozen header, table, borders, banded fills, widths, and formats.

## Latest verified test result
- Full pytest: **175 passed** in 12.33 seconds.
- Python compilation: **passed** for `app.py`, `src`, `config`, `scripts`, and `tests`.

## Files directly involved in the verified bucket/export milestone
- `app.py`
- `src/rca_consolidator/validation/bucket_validator.py`
- `src/rca_consolidator/export/excel_formatter.py`
- `src/rca_consolidator/export/excel_writer.py`
- `tests/test_app.py`
- `tests/test_validation/test_bucket_validator.py`
- `tests/test_export/test_excel_writer.py`

## Not verified or not implemented
- The pairwise bucket mapping is based on a previously transcribed workbook mapping. The actual `Final Buckets & Sub Bucket bucketization.xlsx` reference workbook was not available in this workspace, so every mapping/spelling has not been independently re-opened and checked.
- The export is implementation-based presentation styling, not pixel-perfect/manual comparison against the November master workbook.
- No `CircleFocused` or `RCA Summary` sheet is implemented.
- No standalone validation-report workbook sheet is implemented.
- Bucket mismatch blocking or explicit approval remains a workflow decision; current behavior is informational/reporting only.
- No manual acceptance test was recorded against real source workbooks in this verification run.

## Manual acceptance checklist
- [ ] Only `RCA_Data` is read.
- [ ] Header detected in the first five rows.
- [ ] Missing/ambiguous headers flagged.
- [ ] Fuzzy mappings require approval.
- [ ] Circle rule fills only missing Project cells.
- [ ] Existing Project values are preserved.
- [ ] Reporting date is required.
- [ ] Sequential date, O&M, and outage filters remain correct.
- [ ] Exact duplicates are removed and counted.
- [ ] Bucket pairs match the actual verified reference workbook.
- [ ] Export appearance matches the November master workbook.
- [ ] Uploaded files remain unchanged.
