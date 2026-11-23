"""Tests for cell-level validation of cleaned RCA data."""

from io import BytesIO

import pandas as pd
import pytest
from openpyxl import Workbook

from config.column_schema import MANDATORY_COLUMNS
from rca_consolidator.ingestion.excel_reader import read_rca_data
from rca_consolidator.processing.data_cleaner import clean_dataframe
from rca_consolidator.validation.data_validator import (
    validate_cleaned_dataframe,
)
from tests.test_ingestion.conftest import NamedBytesIO


def _row(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        column: f"value-{index}" for index, column in enumerate(MANDATORY_COLUMNS)
    }
    values.update(overrides)
    return values


def test_validation_reports_blank_cells_with_row_position_and_column() -> None:
    source = pd.DataFrame(
        [
            _row(Circle="North"),
            _row(Circle="  ", **{"Site ID": None}),
        ],
        index=[10, 20],
    )

    result = validate_cleaned_dataframe(clean_dataframe(source))

    assert not result.is_valid
    assert [(issue.row_position, issue.dataframe_index, issue.column)
            for issue in result.blank_cells] == [
        (1, 20, "Circle"),
        (1, 20, "Site ID"),
    ]


def test_validation_reports_ambiguous_date_without_changing_it() -> None:
    source = pd.DataFrame([_row(Date="03/04/2025")])
    cleaned = clean_dataframe(source)

    result = validate_cleaned_dataframe(cleaned)

    assert len(result.unsupported_dates) == 1
    assert result.unsupported_dates[0].value == "03/04/2025"
    assert cleaned.loc[0, "Date"] == "03/04/2025"


def test_validation_rejects_missing_or_misordered_schema_columns() -> None:
    cleaned = clean_dataframe(pd.DataFrame([_row()]))
    misordered = cleaned.loc[:, list(reversed(MANDATORY_COLUMNS))]

    with pytest.raises(ValueError, match="exactly the mandatory columns"):
        validate_cleaned_dataframe(misordered)


def test_site_id_format_findings_flow_into_data_validation_result() -> None:
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "RCA_Data"
    worksheet.append(list(MANDATORY_COLUMNS))
    source_row = _row(Date="2025-02-03", **{"Site ID": 123})
    values = [source_row[column] for column in MANDATORY_COLUMNS]
    worksheet.append(values)
    worksheet.cell(2, MANDATORY_COLUMNS.index("Site ID") + 1).number_format = (
        "000000.00"
    )
    payload = BytesIO()
    workbook.save(payload)
    uploaded_file = NamedBytesIO(payload.getvalue(), "site-id.xlsx")

    source = read_rca_data(uploaded_file)
    result = validate_cleaned_dataframe(clean_dataframe(source))

    assert result.is_valid
    assert result.requires_review
    assert len(result.site_id_format_findings) == 1
    assert result.site_id_format_findings[0].number_format == "000000.00"
