"""Streamlit upload-validation workflow tests."""

from io import BytesIO
from datetime import date
from pathlib import Path

import pandas as pd
from openpyxl import Workbook
from streamlit.testing.v1 import AppTest

from config.column_schema import MANDATORY_COLUMNS


APP_PATH = Path(__file__).resolve().parents[1] / "app.py"
EXCEL_MIME_TYPE = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)


def _workbook_bytes(
    columns: list[str],
    values: dict[str, str] | list[dict[str, str]],
    *,
    header_row: int = 1,
) -> bytes:
    workbook = BytesIO()
    rows = values if isinstance(values, list) else [values]
    dataframe = pd.DataFrame(
        [
            {
                **{column: row.get(column, "value") for column in columns},
                "Date": row.get("Date", "2025-01-01"),
                "O&M Start (Yes/No)": row.get("O&M Start (Yes/No)", "Yes"),
                "Outage Min.": row.get("Outage Min.", 15),
            }
            for row in rows
        ]
    )
    with pd.ExcelWriter(workbook, engine="openpyxl") as writer:
        dataframe.to_excel(
            writer,
            sheet_name="RCA_Data",
            index=False,
            startrow=header_row - 1,
        )
    return workbook.getvalue()


def _ambiguous_workbook_bytes() -> bytes:
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "RCA_Data"
    worksheet.append(list(MANDATORY_COLUMNS))
    worksheet.append(["cover"] * len(MANDATORY_COLUMNS))
    worksheet.append(list(MANDATORY_COLUMNS))
    worksheet.append(
        [
            "2025-01-01" if column == "Date"
            else "LWE" if column == "Project"
            else "value"
            for column in MANDATORY_COLUMNS
        ]
    )
    content = BytesIO()
    workbook.save(content)
    return content.getvalue()


def _validate_upload(filename: str, content: bytes) -> AppTest:
    app = AppTest.from_file(str(APP_PATH)).run()
    app.file_uploader[0].set_value(
        [(filename, content, EXCEL_MIME_TYPE)]
    ).run()
    validate_button = next(
        button for button in app.button if button.label == "Validate Workbooks"
    )
    validate_button.click().run()
    return app


def test_app_startup_imports_project_validator_helpers() -> None:
    app = AppTest.from_file(str(APP_PATH)).run()

    assert not app.exception
    assert any("No files have been uploaded" in item.value for item in app.info)


def test_validate_workbooks_displays_valid_schema_and_project() -> None:
    content = _workbook_bytes(
        list(MANDATORY_COLUMNS),
        {"Project": "LWE"},
    )

    app = _validate_upload("valid.xlsx", content)

    assert not app.exception
    assert any(item.label == "VALID | valid.xlsx" for item in app.expander)
    assert any(
        "**Project identity status:** VALID (LWE)" in item.value
        for item in app.markdown
    )
    assert len(app.date_input) == 1
    assert app.date_input[0].value is None
    start_button = next(
        button for button in app.button if button.label == "Start Consolidation"
    )
    assert start_button.disabled
    app.date_input[0].set_value(date(2025, 1, 1)).run()
    start_button = next(
        button for button in app.button if button.label == "Start Consolidation"
    )
    assert not start_button.disabled


def test_bucket_validation_reports_per_file_batch_and_source_rows() -> None:
    content = _workbook_bytes(
        list(MANDATORY_COLUMNS),
        [
            {
                "Project": "LWE",
                "Final Bucket": "TCS",
                "Bucket - 2": "Fluctuation",
                "RCA": "valid",
            },
            {
                "Project": "LWE",
                "Final Bucket": "Others",
                "Bucket - 2": "Nokia mini link",
                "RCA": "invalid",
            },
        ],
    )
    second_content = _workbook_bytes(
        list(MANDATORY_COLUMNS),
        {
            "Project": "LWE",
            "Final Bucket": "HFCL",
            "Bucket - 2": "Fluctuation",
        },
    )
    app = AppTest.from_file(str(APP_PATH)).run()
    app.file_uploader[0].set_value(
        [
            ("buckets.xlsx", content, EXCEL_MIME_TYPE),
            ("valid-buckets.xlsx", second_content, EXCEL_MIME_TYPE),
        ]
    ).run()
    next(
        button for button in app.button if button.label == "Validate Workbooks"
    ).click().run()

    assert not app.exception
    assert any(item.value == "Bucket Validation" for item in app.subheader)
    per_file = next(
        dataframe.value
        for dataframe in app.dataframe
        if {"Valid records", "Invalid records"}.issubset(
            dataframe.value.columns
        )
    )
    assert per_file["Filename"].tolist() == [
        "buckets.xlsx",
        "valid-buckets.xlsx",
    ]
    assert per_file.loc[0, "Valid records"] == 1
    assert per_file.loc[0, "Invalid records"] == 1
    assert per_file.loc[1, "Valid records"] == 1
    assert per_file.loc[1, "Invalid records"] == 0
    batch_counts = app.json[0].value
    assert 'valid records": 2' in batch_counts
    assert 'invalid records": 1' in batch_counts

    findings = next(
        dataframe.value
        for dataframe in app.dataframe
        if "Excel row number" in dataframe.value.columns
    )
    assert findings.loc[0, "Source filename"] == "buckets.xlsx"
    assert findings.loc[0, "Excel row number"] == 3
    assert findings.loc[0, "Final Bucket"] == "Others"
    assert findings.loc[0, "Bucket - 2"] == "Nokia mini link"
    assert "not allowed" in findings.loc[0, "Error reason"]
    assert [
        uploaded_file.getvalue() for uploaded_file in app.file_uploader[0].value
    ] == [content, second_content]


def test_validate_workbooks_flags_missing_project_without_filling_it() -> None:
    columns = [column for column in MANDATORY_COLUMNS if column != "Project"]
    content = _workbook_bytes(columns, {})

    app = _validate_upload("missing-project.xlsx", content)

    assert not app.exception
    assert any(
        item.label == "INVALID | missing-project.xlsx" for item in app.expander
    )
    assert any(
        "**Project identity status:** MISSING_COLUMN" in item.value
        for item in app.markdown
    )
    assert any(
        "Project column is missing" in item.value for item in app.warning
    )
    assert any(item.label == "Project assignment" for item in app.selectbox)


def test_circle_match_assigns_missing_project_without_manual_approval() -> None:
    columns = [column for column in MANDATORY_COLUMNS if column != "Project"]
    content = _workbook_bytes(
        columns,
        {"Circle": "North 4G---SAturation Circle", "RCA": "circle-match"},
    )
    app = _validate_upload("circle-match.xlsx", content)

    assert not app.exception
    assert any(item.label == "VALID | circle-match.xlsx" for item in app.expander)
    assert any(
        "Project automatically assigned as '4G Saturation' from Circle"
        in item.value
        for item in app.success
    )
    assert any("data rows [1]" in item.value for item in app.success)
    assert not any(item.label == "Project assignment" for item in app.selectbox)

    app.date_input[0].set_value(date(2025, 1, 1)).run()
    next(
        button for button in app.button if button.label == "Start Consolidation"
    ).click().run()

    consolidated = next(
        dataframe.value
        for dataframe in app.dataframe
        if "Project" in dataframe.value.columns
    )
    assert consolidated["Project"].tolist() == ["4G Saturation"]
    assert app.file_uploader[0].value[0].getvalue() == content


def test_unrelated_or_missing_circle_keeps_manual_project_assignment_required() -> None:
    columns = [column for column in MANDATORY_COLUMNS if column != "Project"]
    unrelated = _workbook_bytes(columns, {"Circle": "North"})
    missing = _workbook_bytes(columns, {"Circle": None})
    app = AppTest.from_file(str(APP_PATH)).run()
    app.file_uploader[0].set_value(
        [
            ("unrelated.xlsx", unrelated, EXCEL_MIME_TYPE),
            ("missing-circle.xlsx", missing, EXCEL_MIME_TYPE),
        ]
    ).run()

    assert not app.exception
    assert any(item.label == "INVALID | unrelated.xlsx" for item in app.expander)
    assert any(
        item.label == "INVALID | missing-circle.xlsx" for item in app.expander
    )
    assert not any(
        "Project automatically assigned as '4G Saturation' from Circle"
        in item.value
        for item in app.success
    )
    assert sum(item.label == "Project assignment" for item in app.selectbox) == 2
    assert next(
        button for button in app.button if button.label == "Start Consolidation"
    ).disabled


def test_per_file_header_rows_and_project_corrections_gate_consolidation() -> None:
    dta1_columns = [
        column for column in MANDATORY_COLUMNS if column != "Project"
    ]
    dta1_content = _workbook_bytes(
        dta1_columns,
        {"Date": "2025-01-02", "RCA": "missing-project"},
        header_row=3,
    )
    dta2_content = _workbook_bytes(
        list(MANDATORY_COLUMNS),
        {"Date": "2025-01-02", "Project": "4G-Saturation", "RCA": "correct-me"},
    )
    lwe_content = _workbook_bytes(
        list(MANDATORY_COLUMNS),
        {"Date": "2025-01-02", "Project": "LWE", "RCA": "keep-lwe"},
    )
    app = AppTest.from_file(str(APP_PATH)).run()
    app.file_uploader[0].set_value(
        [
            ("dta1.xlsx", dta1_content, EXCEL_MIME_TYPE),
            ("dta2.xlsx", dta2_content, EXCEL_MIME_TYPE),
            ("lwe.xlsx", lwe_content, EXCEL_MIME_TYPE),
        ]
    ).run()

    assert any(item.label == "INVALID | dta1.xlsx" for item in app.expander)
    assert any(item.label == "INVALID | dta2.xlsx" for item in app.expander)
    summary = next(
        dataframe.value
        for dataframe in app.dataframe
        if "Excel header row" in dataframe.value.columns
    )
    assert (
        summary.loc[summary["Filename"] == "dta1.xlsx", "Excel header row"].iloc[0]
        == 3
    )
    assert (
        summary.loc[summary["Filename"] == "dta2.xlsx", "Excel header row"].iloc[0]
        == 1
    )
    start_button = next(
        button for button in app.button if button.label == "Start Consolidation"
    )
    assert start_button.disabled

    app.selectbox[0].set_value("4G Saturation").run()
    next(
        button
        for button in app.button
        if button.label == "Approve Project assignment for dta1.xlsx"
    ).click().run()
    assert any(item.label == "VALID | dta1.xlsx" for item in app.expander)
    assert next(
        button for button in app.button if button.label == "Start Consolidation"
    ).disabled

    next(
        button
        for button in app.button
        if button.label == "Approve suggested correction for dta2.xlsx"
    ).click().run()
    assert any(item.label == "VALID | dta2.xlsx" for item in app.expander)
    assert any(
        "Approved Project correction: '4G-Saturation' → '4G Saturation'"
        in item.value
        for item in app.success
    )
    assert any(item.label == "VALID | lwe.xlsx" for item in app.expander)
    start_button = next(
        button for button in app.button if button.label == "Start Consolidation"
    )
    assert start_button.disabled
    app.date_input[0].set_value(date(2025, 1, 2)).run()
    start_button = next(
        button for button in app.button if button.label == "Start Consolidation"
    )
    assert not start_button.disabled

    next(
        button for button in app.button if button.label == "Start Consolidation"
    ).click().run()
    assert any(
        "**Batch status:** SUCCESS" in item.value for item in app.markdown
    )
    filter_report = next(
        dataframe.value
        for dataframe in app.dataframe
        if "After outage filter" in dataframe.value.columns
    )
    assert filter_report["Filename"].tolist() == [
        "dta1.xlsx",
        "dta2.xlsx",
        "lwe.xlsx",
    ]
    assert filter_report["After duplicate removal"].tolist() == [1, 1, 1]
    consolidated = next(
        dataframe.value
        for dataframe in app.dataframe
        if "Project" in dataframe.value.columns
    )
    assert set(consolidated["Project"]) == {"LWE", "4G Saturation"}
    assert consolidated["Project"].tolist().count("LWE") == 1
    assert [
        uploaded_file.getvalue()
        for uploaded_file in app.file_uploader[0].value
    ] == [dta1_content, dta2_content, lwe_content]


def test_ambiguous_header_detection_requires_manual_row_selection() -> None:
    content = _ambiguous_workbook_bytes()
    app = _validate_upload("ambiguous.xlsx", content)

    assert any(
        item.label == "REVIEW REQUIRED | ambiguous.xlsx" for item in app.expander
    )
    assert any(
        "candidate Excel rows: 1, 3" in item.value
        for item in app.warning
    )
    assert next(
        button for button in app.button if button.label == "Start Consolidation"
    ).disabled

    app.selectbox[0].set_value(3).run()
    next(
        button
        for button in app.button
        if button.label == "Use selected header row for ambiguous.xlsx"
    ).click().run()

    assert any(item.label == "VALID | ambiguous.xlsx" for item in app.expander)
    assert any(
        "**Excel header row:** 3" in item.value for item in app.markdown
    )


def test_rejected_project_correction_keeps_original_and_blocks_consolidation() -> None:
    content = _workbook_bytes(
        list(MANDATORY_COLUMNS),
        {"Date": "2025-01-02", "Project": "4G-Saturation"},
    )
    app = _validate_upload("dta2.xlsx", content)

    assert any(
        "Original value" in item.value and "4G-Saturation" in item.value
        for item in app.json
    )
    assert next(
        button for button in app.button if button.label == "Start Consolidation"
    ).disabled

    next(
        button
        for button in app.button
        if button.label == "Reject suggested correction for dta2.xlsx"
    ).click().run()

    assert any(item.label == "INVALID | dta2.xlsx" for item in app.expander)
    assert any(
        "Project correction was rejected" in item.value for item in app.warning
    )
    assert app.file_uploader[0].value[0].getvalue() == content
    assert next(
        button for button in app.button if button.label == "Start Consolidation"
    ).disabled
