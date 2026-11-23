# AI Project Context

## Purpose
Build a reliable daily workflow that accepts multiple circle-wise Excel workbooks, validates structure and business identity, filters eligible RCA records, consolidates them, reports data-quality issues, and exports a consistently formatted Excel workbook.

## Intended workflow
1. Upload one or more Excel workbooks.
2. Read only worksheet `RCA_Data`.
3. Detect header row within first five Excel rows.
4. Validate schema and column mappings.
5. Resolve Project identity.
6. Validate `Final Bucket` + `Bucket - 2` consistency.
7. Select reporting date.
8. Filter by selected date, O&M Start = Yes, and Outage Min. > 0.
9. Consolidate and remove exact duplicates.
10. Generate validation/processing reports.
11. Export formatted Excel.

## Known technology
Python, Pandas, OpenPyXL, Streamlit, Pytest, and RapidFuzz (where used). Confirm actual versions in `requirements.txt` and `pyproject.toml`.

## Architecture direction
Keep UI, ingestion, header detection, schema mapping, Project validation, record filtering, duplicate handling, bucket validation, consolidation, reporting, and Excel export/formatting in separate modules.

## Learning approach
Explain why a module or design choice exists. Prefer small, testable changes over large unexplained code dumps.
