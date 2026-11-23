# Copilot Instructions

## Project context

RCA Consolidation System is planned to consolidate telecom Root Cause Analysis
(RCA) Excel data received from multiple circles. The eventual workflow will
read only `RCA_Data`, retain 12 mandatory columns, reject missing required
columns, suggest spelling corrections for user confirmation, consolidate
records, remove exact duplicates using all standardized columns, produce
circle-wise and overall summaries plus a validation report, and export a
formatted workbook.

The `Circle` column in `RCA_Data` is the authoritative Circle source. It is
mandatory; a missing column fails schema validation. Do not require manual
Circle selection during normal uploads or overwrite worksheet values with a
selected Circle. Flag blank Circle values in validation results without
silently filling them. Preserve original Circle values during consolidation;
do not automatically rename or correct them. Do not assume a workbook contains
only one Circle unless a separate business rule establishes that.

File ingestion, column mapping, schema validation, standalone DataFrame cleaning,
and cell-level value validation are implemented. These modules are not yet wired
into an end-to-end upload and consolidation workflow. Remaining capabilities
are planned and must not be treated as already available.

## Architecture principles

- Keep the `src`-based `rca_consolidator` package.
- Separate UI, ingestion, processing, validation, reporting, export, services,
  utilities, and top-level configuration.
- Keep core business rules independently testable and UI-independent.
- Keep configuration centralized; avoid coupling business rules to Streamlit
  or Excel file-format details.
- Prefer cohesive modules with a single responsibility and avoid unnecessary
  classes or abstractions.

## Coding standards

- Use clear, idiomatic, type-annotated Python for implementation.
- Follow existing conventions and add focused pytest coverage for new behavior.
- Reuse existing dependencies and helpers; do not add dependencies without need.
- Surface invalid inputs and operational errors explicitly.
- Keep documentation aligned with architecture and implemented behavior.

## Scope control

- Implement only functionality explicitly requested by the user.
- Do not add business logic, workbook reading or writing, a working Streamlit
  interface, sample datasets, or speculative abstractions as part of scaffolding.
- Before changing existing files, inspect them and preserve useful work.
