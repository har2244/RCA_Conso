# Changelog

## 2026-11-23 — Verified bucket reporting and formatted Excel export
- Implemented pairwise `Final Bucket` + `Bucket - 2` validation in `src/rca_consolidator/validation/bucket_validator.py`.
- Added Streamlit per-file and batch bucket findings in `app.py`, including source filename and Excel row provenance.
- Added formatted `RCA_Data` workbook export in `src/rca_consolidator/export/excel_formatter.py` and `src/rca_consolidator/export/excel_writer.py`.
- Export behavior includes schema-order validation, date formatting, text-preserved Site ID, numeric Outage Min., frozen header, table autofilter, borders, and banded fills.
- Bucket mismatches remain informational and do not silently correct values or block consolidation in the current implementation.
- Files involved: `app.py`, `src/rca_consolidator/validation/bucket_validator.py`, `src/rca_consolidator/export/excel_formatter.py`, `src/rca_consolidator/export/excel_writer.py`, `tests/test_app.py`, `tests/test_validation/test_bucket_validator.py`, `tests/test_export/test_excel_writer.py`.
- Verification: full pytest result was 175 passed; Python compilation completed successfully.
- Limitations: the pairwise mapping was not re-opened against the actual reference workbook, and formatting was not manually compared pixel-for-pixel with the November master workbook.

## 2026-11-23 — Cross-tool AI handoff documentation
- Added portable project context, business rules, architecture, decisions, status, and handoff instructions.
- Recorded bucket mapping as provisional pending source-workbook verification.
- Recorded bucket validation and Excel formatting as pending, not implemented.

## 2026-11-20 — Latest reported implementation (from user-provided Copilot report)
- Added Circle-based automatic Project assignment for missing Project cells when Circle contains recognized 4G Satu / 4G Saturation variants.
- Existing nonblank Project values preserved.
- Unrelated or blank Circle values remain on manual-resolution path.
- Reported verification: 167 tests passed; Python compilation passed.

## Earlier milestones (exact dates/commits not independently verified)
- Header detection within first five rows.
- Project identity validation and approval workflow.
- Reporting-date selection.
- Date, O&M Start = Yes, and Outage Min. > 0 filters.
- Per-file and batch filter reporting.
- Consolidation and exact duplicate removal.

## Update convention
Add newest entry at top. Include date, user-visible behaviour, files changed, tests and exact result, manual verification, and known limitations.
