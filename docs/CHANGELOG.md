# Changelog

## 2026-11-23 — Verified bucket reporting and formatted Excel export
- Implemented pairwise `Final Bucket` + `Bucket - 2` validation in `src/rca_consolidator/validation/bucket_validator.py`.
- Added per-file and batch bucket findings to `app.py`, including source filename and Excel row provenance.
- Added formatted `RCA_Data` workbook export in `src/rca_consolidator/export/excel_formatter.py` and `src/rca_consolidator/export/excel_writer.py`.
- Export behavior includes canonical 12-column validation, date formatting, text-preserved Site ID, numeric Outage Min., frozen header, Excel Table, borders, and banded fills.
- Bucket mismatches are not corrected and do not block consolidation in the current implementation.
- Verification: 175 pytest tests passed; Python compilation passed.
- Limitations: the actual bucket reference workbook was unavailable for mapping verification, and the November master workbook was unavailable for pixel-perfect visual comparison.
