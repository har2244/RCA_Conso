# Technical Architecture — Working Reference

## Principles
- Keep business logic outside Streamlit UI.
- Keep functions small and testable.
- Use Pandas for tabular processing and OpenPyXL for workbook operations where appropriate.
- Keep reference mappings/configuration separate from UI.
- Operate on in-memory copies; preserve uploaded source bytes.
- Revalidate after approved transformations.
- Export only after validation, filtering, deduplication, and consolidation.

## Known layout (verify against actual repository)
```text
project-root/
├── app.py
├── config/
├── src/rca_consolidator/
│   ├── ingestion/
│   ├── processing/
│   ├── validation/
│   ├── reporting/
│   ├── export/
│   ├── services/
│   ├── ui/
│   └── utils/
├── tests/
├── scripts/
├── docs/
├── data/
├── logs/
├── requirements.txt
└── pyproject.toml
```

## Known module areas from prior reports
- `app.py`: Streamlit workflow/UI.
- `project_validator.py`: Project identity helpers (verify actual path).
- `record_filter.py`: reporting-date, O&M and outage filters (reported new module).
- `consolidation_service.py`: consolidation orchestration (verify path).
- `header_detector.py`: header detection within first five rows (reported new module).
- `validation/bucket_validator.py`: pairwise Final Bucket/Bucket - 2 validation.
- `export/excel_formatter.py`: applies worksheet presentation and Table settings.
- `export/excel_writer.py`: serializes consolidated records to formatted workbook bytes.

Do not rely on exact paths until inspected.
