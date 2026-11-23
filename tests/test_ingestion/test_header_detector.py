"""Tests for automatic RCA worksheet header detection."""

from io import BytesIO
from typing import Sequence

from openpyxl import Workbook
import pandas as pd
import pytest

from config.column_schema import MANDATORY_COLUMNS
from rca_consolidator.ingestion.excel_reader import (
    AmbiguousHeaderRowError,
    HEADER_ROW_ATTR,
    HeaderNotDetectedError,
    read_rca_data,
)
from rca_consolidator.ingestion.header_detector import (
    HeaderDetectionStatus,
    detect_header_row,
)
from rca_consolidator.services.consolidation_service import (
    FileProcessingStatus,
    prepare_files,
)
from tests.test_ingestion.conftest import NamedBytesIO


def _upload(
    filename: str,
    header_rows: Sequence[tuple[int, Sequence[object]]],
) -> NamedBytesIO:
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "RCA_Data"
    for row_number, values in header_rows:
        for column_number, value in enumerate(values, start=1):
            worksheet.cell(row=row_number, column=column_number, value=value)
    worksheet.append(["row-value"] * len(MANDATORY_COLUMNS))

    content = BytesIO()
    workbook.save(content)
    return NamedBytesIO(content.getvalue(), filename)


@pytest.mark.parametrize("header_row", [1, 2, 3, 4, 5])
def test_auto_detects_headers_in_each_of_the_first_five_rows(
    header_row: int,
) -> None:
    upload = _upload(
        "offset.xlsx",
        [(header_row, MANDATORY_COLUMNS)],
    )

    data = read_rca_data(upload, header_row=None)

    assert tuple(data.columns) == MANDATORY_COLUMNS
    assert data.attrs[HEADER_ROW_ATTR] == header_row


def test_rejects_header_beyond_the_first_five_rows() -> None:
    upload = _upload(
        "late-header.xlsx",
        [(6, MANDATORY_COLUMNS)],
    )

    with pytest.raises(
        HeaderNotDetectedError,
        match="Header not detected within the first 5 rows.",
    ):
        read_rca_data(upload, header_row=None)

    prepared = prepare_files([upload]).files[0]
    assert prepared.status is FileProcessingStatus.INVALID_SCHEMA
    assert prepared.error == "Header not detected within the first 5 rows."
    assert prepared.header_row is None


def test_equal_header_rows_are_flagged_for_manual_review_without_guessing() -> None:
    upload = _upload(
        "ambiguous.xlsx",
        [(1, MANDATORY_COLUMNS), (3, MANDATORY_COLUMNS)],
    )
    preview = pd.DataFrame(
        [
            list(MANDATORY_COLUMNS),
            ["title"] * len(MANDATORY_COLUMNS),
            list(MANDATORY_COLUMNS),
        ]
    )

    detection = detect_header_row(preview)

    assert detection.status is HeaderDetectionStatus.AMBIGUOUS
    assert detection.header_row is None
    assert detection.candidate_rows == (1, 3)
    with pytest.raises(AmbiguousHeaderRowError, match="Manual review is required"):
        read_rca_data(upload, header_row=None)

    prepared = prepare_files([upload]).files[0]
    assert prepared.status is FileProcessingStatus.PENDING_HEADER_REVIEW
    assert prepared.source_dataframe is None
    assert prepared.header_candidates == (1, 3)


def test_full_header_outscores_an_incorrect_partial_header_row() -> None:
    upload = _upload(
        "incorrect-first-row.xlsx",
        [
            (1, MANDATORY_COLUMNS[:6]),
            (3, MANDATORY_COLUMNS),
        ],
    )

    data = read_rca_data(upload, header_row=None)

    assert data.attrs[HEADER_ROW_ATTR] == 3
    assert tuple(data.columns) == MANDATORY_COLUMNS


def test_fuzzy_header_match_detects_row_but_still_requires_mapping_approval() -> None:
    headers = list(MANDATORY_COLUMNS)
    headers[1] = "Projec"
    upload = _upload("fuzzy-header.xlsx", [(1, headers)])

    prepared = prepare_files([upload]).files[0]

    assert prepared.header_row == 1
    assert prepared.status is FileProcessingStatus.PENDING_MAPPING_APPROVAL
    assert prepared.schema_validation is not None
    assert prepared.schema_validation.mapping_result.suggestions
