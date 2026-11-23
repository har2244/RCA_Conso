"""Tests for required worksheet identification."""

from rca_consolidator.ingestion.sheet_detector import detect_rca_data_sheet
from tests.test_ingestion.conftest import NamedBytesIO, workbook_bytes


def test_detects_exact_rca_data_sheet() -> None:
    uploaded_file = NamedBytesIO(
        workbook_bytes({"RCA_Data": [["Site ID"]], "Other": [["ignored"]]}),
        "source.xlsx",
    )
    uploaded_file.seek(3)

    result = detect_rca_data_sheet(uploaded_file)

    assert result.found
    assert result.sheet_name == "RCA_Data"
    assert result.error is None
    assert result.filename == "source.xlsx"
    assert uploaded_file.tell() == 3


def test_reports_missing_rca_data_sheet() -> None:
    uploaded_file = NamedBytesIO(workbook_bytes({"Other": [["value"]]}), "source.xlsx")

    result = detect_rca_data_sheet(uploaded_file)

    assert not result.found
    assert result.sheet_name is None
    assert "Worksheet 'RCA_Data' was not found" in result.error


def test_reports_corrupted_workbook() -> None:
    uploaded_file = NamedBytesIO(b"not an Excel workbook", "corrupt.xlsx")

    result = detect_rca_data_sheet(uploaded_file)

    assert not result.found
    assert result.error is not None
    assert "Could not inspect workbook" in result.error
