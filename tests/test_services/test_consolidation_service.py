"""Tests for UI-independent per-file preparation and consolidation."""

from datetime import date, datetime
from io import BytesIO
from typing import Mapping, Sequence

import pandas as pd
import pytest
from openpyxl import Workbook

from config.column_schema import MANDATORY_COLUMNS
from rca_consolidator.services.consolidation_service import (
    ConsolidationStatus,
    FileProcessingStatus,
    PreparedBatchResult,
    consolidate_prepared_files,
    prepare_files,
)
from tests.test_ingestion.conftest import NamedBytesIO, workbook_bytes

REPORTING_DATE = date(2025, 2, 3)


def _row(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        column: f"value-{index}" for index, column in enumerate(MANDATORY_COLUMNS)
    }
    values["Date"] = "2025-02-03"
    values["Site ID"] = "00123"
    values["O&M Start (Yes/No)"] = "Yes"
    values["Outage Min."] = 15
    values.update(overrides)
    return values


def _consolidate(
    prepared_batch: PreparedBatchResult,
    mapping_decisions_by_file: Mapping[int, Mapping[int, str | None]] | None = None,
):
    return consolidate_prepared_files(
        prepared_batch,
        mapping_decisions_by_file,
        reporting_date=REPORTING_DATE,
    )


def _upload(
    filename: str,
    rows: Sequence[Mapping[str, object]] = (),
    *,
    headers: Sequence[str] = MANDATORY_COLUMNS,
    header_aliases: Mapping[str, str] | None = None,
    header_row: int = 1,
    site_id_formats: Mapping[int, str] | None = None,
) -> NamedBytesIO:
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "RCA_Data"
    if header_row == 2:
        worksheet.append(["Title"])
    worksheet.append(list(headers))

    site_id_formats = site_id_formats or {}
    site_id_column = (
        list(headers).index("Site ID") + 1
        if "Site ID" in headers
        else None
    )
    for row_position, row in enumerate(rows):
        worksheet.append(
            [
                row.get((header_aliases or {}).get(header, header))
                for header in headers
            ]
        )
        if row_position in site_id_formats and site_id_column is not None:
            worksheet.cell(
                row=worksheet.max_row,
                column=site_id_column,
            ).number_format = site_id_formats[row_position]

    payload = BytesIO()
    workbook.save(payload)
    return NamedBytesIO(payload.getvalue(), filename)


def test_multiple_valid_files_keep_upload_order_and_track_provenance() -> None:
    first = _upload("same.xlsx", [_row(Project="first")])
    second = _upload("same.xlsx", [_row(Project="second")])

    prepared = prepare_files([first, second])
    result = _consolidate(prepared)

    assert result.status is ConsolidationStatus.SUCCESS
    assert [file.file_index for file in result.file_results] == [0, 1]
    assert [file.status for file in result.file_results] == [
        FileProcessingStatus.PROCESSED,
        FileProcessingStatus.PROCESSED,
    ]
    assert result.dataframe["Project"].tolist() == ["first", "second"]
    assert [
        (row.file_index, row.filename, row.source_row_position)
        for row in result.row_provenance
    ] == [(0, "same.xlsx", 0), (1, "same.xlsx", 0)]


def test_mixed_valid_and_invalid_files_preserve_successful_results() -> None:
    valid = _upload("valid.xlsx", [_row(Project="valid")])
    invalid_extension = NamedBytesIO(b"bad", "invalid.csv")

    result = _consolidate(
        prepare_files([valid, invalid_extension])
    )

    assert result.status is ConsolidationStatus.PARTIAL_SUCCESS
    assert result.dataframe["Project"].tolist() == ["valid"]
    assert result.file_results[0].is_successful
    assert result.file_results[1].status is FileProcessingStatus.FAILED
    assert "Unsupported file extension" in result.file_results[1].error


def test_all_invalid_files_return_explicit_empty_batch_result() -> None:
    invalid_extension = NamedBytesIO(b"bad", "invalid.csv")
    missing_sheet = NamedBytesIO(
        workbook_bytes({"Other": [["value"]]}),
        "missing-sheet.xlsx",
    )

    result = _consolidate(
        prepare_files([invalid_extension, missing_sheet])
    )

    assert result.status is ConsolidationStatus.NO_SUCCESSFUL_FILES
    assert result.dataframe.empty
    assert tuple(result.dataframe.columns) == MANDATORY_COLUMNS
    assert result.duplicates_detected == result.duplicates_removed == 0
    assert all(not file.is_successful for file in result.file_results)


def test_header_only_workbook_is_a_successful_empty_input() -> None:
    upload = _upload("headers.xlsx")

    result = _consolidate(prepare_files([upload]))

    assert result.status is ConsolidationStatus.SUCCESS
    assert result.dataframe.empty
    assert tuple(result.dataframe.columns) == MANDATORY_COLUMNS
    assert result.file_results[0].status is FileProcessingStatus.PROCESSED


def test_fuzzy_mapping_stays_pending_until_explicit_approval() -> None:
    headers = list(MANDATORY_COLUMNS)
    headers[1] = "Projec"
    upload = _upload(
        "fuzzy.xlsx",
        [_row(Project="approved")],
        headers=headers,
        header_aliases={"Projec": "Project"},
    )
    prepared = prepare_files([upload])

    pending = _consolidate(prepared)
    approved = _consolidate(
        prepared,
        mapping_decisions_by_file={0: {1: "Project"}},
    )

    assert pending.status is ConsolidationStatus.NO_SUCCESSFUL_FILES
    assert pending.file_results[0].status is FileProcessingStatus.PENDING_MAPPING_APPROVAL
    assert pending.dataframe.empty
    assert approved.status is ConsolidationStatus.SUCCESS
    assert approved.dataframe.loc[0, "Project"] == "approved"


def test_rejected_only_fuzzy_mapping_makes_file_schema_invalid() -> None:
    headers = list(MANDATORY_COLUMNS)
    headers[1] = "Projec"
    prepared = prepare_files(
        [
            _upload(
                "rejected.xlsx",
                [_row(Project="rejected")],
                headers=headers,
                header_aliases={"Projec": "Project"},
            )
        ]
    )

    result = _consolidate(
        prepared,
        mapping_decisions_by_file={0: {1: None}},
    )

    assert result.status is ConsolidationStatus.NO_SUCCESSFUL_FILES
    assert result.file_results[0].status is FileProcessingStatus.INVALID_SCHEMA
    assert result.file_results[0].schema_validation.missing_columns == ("Project",)
    assert result.dataframe.empty


def test_normalized_header_match_uses_existing_automatic_behavior() -> None:
    headers = list(MANDATORY_COLUMNS)
    headers[3] = "Site_ID"
    prepared = prepare_files(
        [
            _upload(
                "normalized.xlsx",
                [_row(Project="normalized")],
                headers=headers,
                header_aliases={"Site_ID": "Site ID"},
            )
        ]
    )

    result = _consolidate(prepared)

    assert result.status is ConsolidationStatus.SUCCESS
    assert result.dataframe.loc[0, "Project"] == "normalized"
    assert tuple(result.dataframe.columns) == MANDATORY_COLUMNS


def test_blank_values_remain_in_output_and_are_reported() -> None:
    upload = _upload("blank.xlsx", [_row(Circle=None)])

    result = _consolidate(prepare_files([upload]))

    assert result.status is ConsolidationStatus.SUCCESS
    assert result.file_results[0].status is (
        FileProcessingStatus.PROCESSED_WITH_VALIDATION_ISSUES
    )
    assert pd.isna(result.dataframe.loc[0, "Circle"])
    assert [
        issue.column
        for issue in result.file_results[0].data_validation.blank_cells
    ] == ["Circle"]
    assert len(result.dataframe) == 1


def test_site_id_format_findings_are_preserved_per_file() -> None:
    first = _upload(
        "unsupported-format.xlsx",
        [_row(**{"Site ID": 12.5})],
        site_id_formats={0: "000000.00"},
    )
    second = _upload("plain.xlsx", [_row(Project="plain")])

    result = _consolidate(prepare_files([first, second]))

    first_validation = result.file_results[0].data_validation
    second_validation = result.file_results[1].data_validation
    assert first_validation.requires_review
    assert len(first_validation.site_id_format_findings) == 1
    assert first_validation.site_id_format_findings[0].workbook_name == (
        "unsupported-format.xlsx"
    )
    assert not second_validation.requires_review
    assert len(result.dataframe) == 2


def test_duplicates_are_removed_once_across_files_with_first_file_provenance() -> None:
    first = _upload("first.xlsx", [_row(Project="shared")])
    second = _upload("second.xlsx", [_row(Project="shared")])

    result = _consolidate(prepare_files([first, second]))

    assert len(result.dataframe) == 1
    assert result.duplicates_detected == result.duplicates_removed == 1
    assert result.dataframe.loc[0, "Project"] == "shared"
    assert len(result.row_provenance) == 1
    assert result.row_provenance[0].file_index == 0
    assert result.row_provenance[0].filename == "first.xlsx"


def test_filters_each_workbook_before_batch_deduplication_and_audits_counts() -> None:
    shared = _row(RCA="shared")
    first = _upload(
        "first.xlsx",
        [
            shared,
            _row(Date="2025-02-04", RCA="other-date"),
            _row(**{"O&M Start (Yes/No)": "No"}, RCA="not-started"),
            _row(**{"Outage Min.": 0}, RCA="no-outage"),
        ],
    )
    second = _upload("second.xlsx", [shared])
    original_bytes = (first.getvalue(), second.getvalue())

    result = _consolidate(prepare_files([first, second]))

    assert result.dataframe["RCA"].tolist() == ["shared"]
    assert tuple(result.dataframe.columns) == MANDATORY_COLUMNS
    assert result.duplicates_removed == 1
    assert result.filter_audit.original_records == 5
    assert result.filter_audit.records_matching_reporting_date == 4
    assert result.filter_audit.records_after_om_filter == 3
    assert result.filter_audit.records_after_outage_filter == 2
    assert result.filter_audit.records_after_duplicate_removal == 1
    assert result.filter_audit.excluded_by_reporting_date == 1
    assert result.filter_audit.excluded_by_om_filter == 1
    assert result.filter_audit.excluded_by_outage_filter == 1
    assert (
        result.filter_audit.original_records
        == result.filter_audit.excluded_by_reporting_date
        + result.filter_audit.excluded_by_om_filter
        + result.filter_audit.excluded_by_outage_filter
        + result.filter_audit.records_after_outage_filter
    )
    assert [
        file_result.filter_audit.records_after_duplicate_removal
        for file_result in result.file_results
    ] == [1, 0]
    assert [
        file_result.filter_audit.duplicates_removed
        for file_result in result.file_results
    ] == [0, 1]
    assert (first.getvalue(), second.getvalue()) == original_bytes


def test_reporting_date_is_required_before_consolidation() -> None:
    prepared = prepare_files([_upload("only.xlsx", [_row()])])

    with pytest.raises(ValueError, match="reporting date"):
        consolidate_prepared_files(prepared)


def test_zero_matching_records_returns_valid_empty_dataset() -> None:
    prepared = prepare_files(
        [_upload("other-date.xlsx", [_row(Date="2025-02-04")])]
    )

    result = _consolidate(prepared)

    assert result.status is ConsolidationStatus.SUCCESS
    assert result.dataframe.empty
    assert tuple(result.dataframe.columns) == MANDATORY_COLUMNS
    assert result.filter_audit.records_after_duplicate_removal == 0


def test_excel_date_and_datetime_cells_match_the_selected_calendar_date() -> None:
    upload = _upload(
        "excel-dates.xlsx",
        [
            _row(Date=date(2025, 2, 3), RCA="excel-date"),
            _row(Date=datetime(2025, 2, 3, 23, 59), RCA="excel-datetime"),
            _row(Date=datetime(2025, 2, 4), RCA="next-date"),
        ],
    )

    result = _consolidate(prepare_files([upload]))

    assert result.dataframe["RCA"].tolist() == ["excel-date", "excel-datetime"]
    assert result.filter_audit.records_matching_reporting_date == 2
    assert result.filter_audit.excluded_by_reporting_date == 1


def test_header_offset_and_original_workbook_bytes_and_positions_are_preserved() -> None:
    upload = _upload(
        "offset.xlsx",
        [_row(Project="offset")],
        header_row=2,
    )
    original_bytes = upload.getvalue()
    upload.seek(7)

    prepared = prepare_files([upload], header_row=2)
    result = _consolidate(prepared)

    assert result.dataframe.loc[0, "Project"] == "offset"
    assert upload.getvalue() == original_bytes
    assert upload.tell() == 7


def test_invalid_mapping_decision_does_not_abort_other_files() -> None:
    headers = list(MANDATORY_COLUMNS)
    headers[1] = "Projec"
    fuzzy = _upload("fuzzy.xlsx", [_row(Project="fuzzy")], headers=headers)
    valid = _upload("valid.xlsx", [_row(Project="valid")])
    prepared = prepare_files([fuzzy, valid])

    result = _consolidate(
        prepared,
        mapping_decisions_by_file={0: {1: "Not a candidate"}},
    )

    assert result.status is ConsolidationStatus.PARTIAL_SUCCESS
    assert result.file_results[0].status is FileProcessingStatus.FAILED
    assert "not a candidate" in result.file_results[0].error
    assert result.file_results[1].is_successful
    assert result.dataframe["Project"].tolist() == ["valid"]


def test_mapping_decision_for_unknown_file_index_is_rejected() -> None:
    prepared = prepare_files([_upload("only.xlsx", [_row()])])

    with pytest.raises(ValueError, match="unknown file indexes"):
        _consolidate(
            prepared,
            mapping_decisions_by_file={7: {1: "Project"}},
        )
