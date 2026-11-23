"""Tests for reading the required RCA worksheet."""

from io import BytesIO

from openpyxl import Workbook
import pytest

from rca_consolidator.ingestion.excel_reader import (
    EmptyWorksheetError,
    ExcelReadError,
    SITE_ID_FORMAT_FINDINGS_ATTR,
    WorksheetNotFoundError,
    read_rca_data,
)
from tests.test_ingestion.conftest import NamedBytesIO, workbook_bytes


@pytest.mark.parametrize("filename", ["source.xlsx", "source.xlsm"])
def test_reads_rca_data_and_preserves_headers_and_text_ids(filename: str) -> None:
    uploaded_file = NamedBytesIO(
        workbook_bytes(
            {
                "Other": [["unrelated"], ["must not be read"]],
                "RCA_Data": [["Site ID", "Original Header"], ["00123", "NA"]],
            }
        ),
        filename,
    )
    uploaded_file.seek(3)

    data = read_rca_data(uploaded_file, text_columns=("Site ID",))

    assert list(data.columns) == ["Site ID", "Original Header"]
    assert data.loc[0, "Site ID"] == "00123"
    assert data.loc[0, "Original Header"] == "NA"
    assert uploaded_file.tell() == 3


def test_numeric_site_id_with_general_format_is_not_changed() -> None:
    uploaded_file = _site_id_workbook([(123, "General")])

    data = read_rca_data(uploaded_file)

    assert data.loc[0, "Site ID"] == 123
    assert isinstance(data.loc[0, "Site ID"], int)
    assert data.attrs[SITE_ID_FORMAT_FINDINGS_ATTR] == ()


def test_numeric_site_id_with_zero_placeholder_format_is_padded() -> None:
    uploaded_file = _site_id_workbook([(123, "000000")])

    data = read_rca_data(uploaded_file)

    assert data.loc[0, "Site ID"] == "000123"
    assert data.attrs[SITE_ID_FORMAT_FINDINGS_ATTR] == ()


@pytest.mark.parametrize(
    ("value", "number_format"),
    [
        (123.5, "000000"),
        (123.5, "000000.00"),
        (-123, "000000"),
        (123, "[>=100]000000;0"),
        (123, "000000;[Red]-000000;0"),
        (123, '000000 "ID"'),
    ],
)
def test_unsupported_site_id_formats_preserve_raw_value_and_add_finding(
    value: int | float,
    number_format: str,
) -> None:
    uploaded_file = _site_id_workbook([(value, number_format)])

    data = read_rca_data(uploaded_file)

    finding, = data.attrs[SITE_ID_FORMAT_FINDINGS_ATTR]
    assert data.loc[0, "Site ID"] == value
    assert finding.row_position == 0
    assert finding.excel_row == 2
    assert finding.cell_coordinate == "A2"
    assert finding.raw_value == value
    assert finding.number_format == number_format


def test_blank_site_id_remains_blank_without_a_format_finding() -> None:
    uploaded_file = _site_id_workbook(
        [(None, "000000")],
        extra_value="keep row",
    )

    data = read_rca_data(uploaded_file)

    assert data.loc[0, "Site ID"] == ""
    assert data.attrs[SITE_ID_FORMAT_FINDINGS_ATTR] == ()


def test_mixed_site_id_types_are_handled_individually() -> None:
    uploaded_file = _site_id_workbook(
        [
            ("00123", "General"),
            (123, "General"),
            (7, "000000"),
            (12.5, "000000.00"),
            (None, "000000"),
        ],
        extra_value="keep row",
    )

    data = read_rca_data(uploaded_file)

    assert data["Site ID"].tolist() == ["00123", 123, "000007", 12.5, ""]
    findings = data.attrs[SITE_ID_FORMAT_FINDINGS_ATTR]
    assert len(findings) == 1
    assert findings[0].row_position == 3


def test_zero_placeholder_format_is_applied_with_header_row_offset() -> None:
    uploaded_file = _site_id_workbook(
        [(123, "000000")],
        header_row=2,
    )

    data = read_rca_data(uploaded_file, header_row=2)

    assert data.loc[0, "Site ID"] == "000123"


def test_site_id_formatting_does_not_change_other_columns() -> None:
    uploaded_file = _site_id_workbook(
        [(123, "000000")],
        extra_value=456,
        extra_number_format="000000",
    )

    data = read_rca_data(uploaded_file)

    assert data.loc[0, "Site ID"] == "000123"
    assert data.loc[0, "Other"] == 456
    assert isinstance(data.loc[0, "Other"], int)


def test_reader_does_not_modify_workbook_bytes_and_restores_stream_position() -> None:
    uploaded_file = _site_id_workbook([(123, "000000")])
    original_bytes = uploaded_file.getvalue()
    uploaded_file.seek(5)

    read_rca_data(uploaded_file)

    assert uploaded_file.getvalue() == original_bytes
    assert uploaded_file.tell() == 5


def test_supports_configurable_one_based_header_row() -> None:
    uploaded_file = NamedBytesIO(
        workbook_bytes({"RCA_Data": [["title"], ["Site ID", "Cause"], ["001", "fault"]]}),
        "source.xlsx",
    )

    data = read_rca_data(uploaded_file, header_row=2)

    assert list(data.columns) == ["Site ID", "Cause"]
    assert data.loc[0, "Site ID"] == "001"


def test_rejects_invalid_header_row() -> None:
    uploaded_file = NamedBytesIO(workbook_bytes({"RCA_Data": [["Site ID"]]}), "source.xlsx")

    with pytest.raises(ValueError, match="positive, one-based"):
        read_rca_data(uploaded_file, header_row=0)


def test_reports_missing_worksheet() -> None:
    uploaded_file = NamedBytesIO(workbook_bytes({"Other": [["value"]]}), "source.xlsx")

    with pytest.raises(WorksheetNotFoundError, match="RCA_Data"):
        read_rca_data(uploaded_file)


def test_reports_fully_empty_worksheet() -> None:
    uploaded_file = NamedBytesIO(workbook_bytes({"RCA_Data": []}), "source.xlsx")

    with pytest.raises(EmptyWorksheetError, match="is empty"):
        read_rca_data(uploaded_file)


def test_allows_header_only_worksheet() -> None:
    uploaded_file = NamedBytesIO(
        workbook_bytes({"RCA_Data": [["Site ID", "Cause"]]}),
        "source.xlsx",
    )

    data = read_rca_data(uploaded_file)

    assert data.empty
    assert list(data.columns) == ["Site ID", "Cause"]


def test_reports_corrupted_workbook() -> None:
    uploaded_file = NamedBytesIO(b"not an Excel workbook", "corrupt.xlsx")

    with pytest.raises(ExcelReadError, match="Could not read worksheet"):
        read_rca_data(uploaded_file)


def _site_id_workbook(
    site_ids: list[tuple[object, str]],
    *,
    header_row: int = 1,
    extra_value: object | None = None,
    extra_number_format: str = "General",
) -> BytesIO:
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "RCA_Data"
    if header_row == 2:
        worksheet.append(["Title"])
    worksheet.append(["Site ID", "Other"])
    for site_id, number_format in site_ids:
        worksheet.append([site_id, extra_value])
        worksheet.cell(worksheet.max_row, 1).number_format = number_format
        worksheet.cell(worksheet.max_row, 2).number_format = extra_number_format

    payload = BytesIO()
    workbook.save(payload)
    payload.seek(0)
    return payload
