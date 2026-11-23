"""Tests for formatted consolidated workbook generation."""

from datetime import datetime
from io import BytesIO

import pandas as pd
from openpyxl import load_workbook
import pytest

from config.column_schema import MANDATORY_COLUMNS
from rca_consolidator.export.excel_writer import write_rca_workbook


def _dataframe() -> pd.DataFrame:
    rows = []
    for row_index in range(3):
        row = {
            column: f"{column}-{row_index}"
            for column in MANDATORY_COLUMNS
        }
        row.update(
            {
                "Date": f"2025-11-0{row_index + 1}",
                "Project": "LWE",
                "Site ID": f"00012{row_index}",
                "Outage Min.": (
                    "2.5" if row_index == 1 else row_index + 1.5
                ),
                "Final Bucket": "TCS",
                "Bucket - 2": "Fluctuation",
            }
        )
        rows.append(row)
    return pd.DataFrame(rows, columns=MANDATORY_COLUMNS)


def test_export_styles_all_records_without_changing_dataframe_values() -> None:
    dataframe = _dataframe()
    original = dataframe.copy(deep=True)

    content = write_rca_workbook(dataframe)
    workbook = load_workbook(BytesIO(content))
    worksheet = workbook["RCA_Data"]

    assert tuple(cell.value for cell in worksheet[1]) == MANDATORY_COLUMNS
    assert worksheet.max_row == 4
    assert worksheet.freeze_panes == "A2"
    assert worksheet.tables["RCADataTable"].ref == "A1:L4"
    table = worksheet.tables["RCADataTable"]
    assert table.autoFilter is not None
    assert table.autoFilter.ref == "A1:L4"
    assert table.tableStyleInfo.name == "TableStyleMedium2"
    assert table.tableStyleInfo.showRowStripes

    header = worksheet["A1"]
    assert header.fill.fgColor.rgb.endswith("12345A")
    assert header.font.bold
    assert header.font.color.rgb.endswith("FFFFFF")
    assert header.alignment.horizontal == "center"
    assert header.alignment.wrap_text
    assert worksheet.row_dimensions[1].height == 36

    assert worksheet["A2"].number_format == "dd-mmm-yyyy"
    assert worksheet["A2"].value == datetime(2025, 11, 1)
    assert worksheet["D2"].value == "000120"
    assert worksheet["D2"].data_type == "s"
    assert worksheet["D2"].number_format == "@"
    assert worksheet["I2"].value == 1.5
    assert isinstance(worksheet["I2"].value, (int, float))
    assert worksheet["I2"].number_format == "0.##"
    assert worksheet["I3"].value == 2.5
    assert isinstance(worksheet["I3"].value, (int, float))

    assert worksheet["A2"].fill.fgColor.rgb.endswith("FFFFFF")
    assert worksheet["A3"].fill.fgColor.rgb.endswith("DDEBF7")
    assert worksheet["A4"].fill.fgColor.rgb.endswith("FFFFFF")
    for row_index in range(1, worksheet.max_row + 1):
        for column_index in range(1, len(MANDATORY_COLUMNS) + 1):
            cell = worksheet.cell(row=row_index, column=column_index)
            assert cell.border.left.style == "thin"
            assert cell.border.left.color.rgb.endswith("000000")
            assert cell.alignment.vertical == "center"
            if row_index > 1:
                assert worksheet.row_dimensions[row_index].height == 30

    pd.testing.assert_frame_equal(dataframe, original)
    assert dataframe["Site ID"].tolist() == ["000120", "000121", "000122"]


def test_empty_export_retains_headers_and_table() -> None:
    dataframe = pd.DataFrame(columns=MANDATORY_COLUMNS)

    content = write_rca_workbook(dataframe)
    worksheet = load_workbook(BytesIO(content))["RCA_Data"]

    assert worksheet.max_row == 1
    assert tuple(cell.value for cell in worksheet[1]) == MANDATORY_COLUMNS
    assert worksheet.tables["RCADataTable"].ref == "A1:L1"
    assert worksheet.freeze_panes == "A2"


def test_export_rejects_noncanonical_column_order() -> None:
    dataframe = _dataframe().loc[:, list(reversed(MANDATORY_COLUMNS))]

    with pytest.raises(ValueError, match="schema order"):
        write_rca_workbook(dataframe)
