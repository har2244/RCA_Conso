# Technical Architecture

The application uses a `src`-based Python package, `rca_consolidator`, with
separate modules for UI, ingestion, processing, validation, reporting, export,
services, and utilities. The top-level `config/` package centralizes
application settings, the column schema, and validation rules.

The `tests/` tree groups tests by application layer. The `data/`, `templates/`,
and `logs/` directories are reserved for runtime artifacts and templates. Keep
business logic independently testable and separate from UI and Excel-format
concerns.

Implemented areas include Excel ingestion, header detection, column mapping,
schema validation, standalone and Streamlit Project validation, DataFrame
cleaning, cell-level validation, pairwise bucket validation, record filtering,
duplicate removal, consolidation orchestration, and formatted `RCA_Data`
workbook export.

Implemented module areas include `ingestion/`, `processing/`,
`validation/bucket_validator.py`, `export/excel_formatter.py`,
`export/excel_writer.py`, and `services/consolidation_service.py`.

Circle summary sheets and standalone workbook reporting sheets are not
implemented.
