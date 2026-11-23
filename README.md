# RCA Consolidation System

Professional Python project scaffold for the planned daily consolidation of
telecom Root Cause Analysis (RCA) workbooks received from multiple circles.

## Status

The project includes a Streamlit workbook-validation and consolidation
workflow, including schema and Project checks, bucket validation, reporting-date
filtering, duplicate removal, and an in-memory formatted Excel download.

## Directory responsibilities

- `src/rca_consolidator/ui/` — Streamlit presentation pages.
- `src/rca_consolidator/ingestion/` — workbook intake and worksheet selection.
- `src/rca_consolidator/processing/` — mapping, cleaning, filtering,
  deduplication, and consolidation.
- `src/rca_consolidator/validation/` — schema, Project, bucket, and data
  validation and correction-review boundaries.
- `src/rca_consolidator/reporting/` — processing and validation reporting
  helpers; circle/overall summary workbook sheets are not implemented.
- `src/rca_consolidator/export/` — formatted Excel workbook generation.
- `src/rca_consolidator/services/` — application workflow orchestration.
- `src/rca_consolidator/utils/` — reusable technical helpers.
- `config/` — centralized settings, schema, and validation rules.
- `templates/` — reserved for workbook templates.
- `data/` — reserved for input, processed, output, and archived files.
- `logs/` — reserved for runtime logs.
- `tests/` — reserved for layer-specific automated tests.
- `docs/` — project overview, architecture, planned business rules, and data
  dictionary.

See [docs/technical_architecture.md](docs/technical_architecture.md) for layer
boundaries and [docs/project_overview.md](docs/project_overview.md) for the
planned workflow.

## Current application scope

The application reads the `RCA_Data` worksheet, validates the 12 mandatory
columns and Project identity, reports Final Bucket/Bucket - 2 mismatches,
filters records for a manually selected reporting date, and removes exact
duplicates across the standardized columns. The Streamlit validation report
includes bucket findings with source filename and Excel row number. Consolidated
records can be downloaded as a formatted `RCA_Data` workbook with a filterable
Excel Table. Summary sheets and advanced workbook styling are not included.

## Development metadata

`requirements.txt` lists the planned runtime and test dependencies.
`pyproject.toml` provides Python package and pytest configuration. Install
dependencies manually when development begins.
