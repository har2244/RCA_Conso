"""Coordinate per-workbook preparation and batch RCA consolidation."""

from collections import Counter
from dataclasses import dataclass, replace
from datetime import date, datetime
from enum import Enum
from typing import BinaryIO, Hashable, Iterable, Mapping, Sequence

import pandas as pd

from config.column_schema import MANDATORY_COLUMNS
from rca_consolidator.ingestion.excel_reader import (
    AmbiguousHeaderRowError,
    ExcelReadError,
    HEADER_ROW_ATTR,
    HeaderNotDetectedError,
    read_rca_data,
)
from rca_consolidator.ingestion.file_handler import validate_uploaded_files
from rca_consolidator.processing.column_mapper import (
    ColumnMappingResult,
    apply_approved_mappings,
    apply_mapping_decisions,
)
from rca_consolidator.processing.consolidation_engine import (
    consolidate_dataframes,
)
from rca_consolidator.processing.data_cleaner import clean_dataframe
from rca_consolidator.processing.record_filter import (
    RecordFilterAudit,
    aggregate_filter_audits,
    filter_rca_records,
)
from rca_consolidator.validation.data_validator import (
    DataValidationResult,
    validate_cleaned_dataframe,
)
from rca_consolidator.validation.schema_validator import (
    SchemaStatus,
    SchemaValidationResult,
    validate_dataframe_schema,
)


class FileProcessingStatus(str, Enum):
    """Preparation or processing outcome for one uploaded workbook."""

    READY = "READY"
    PENDING_MAPPING_APPROVAL = "PENDING_MAPPING_APPROVAL"
    PENDING_HEADER_REVIEW = "PENDING_HEADER_REVIEW"
    INVALID_SCHEMA = "INVALID_SCHEMA"
    FAILED = "FAILED"
    PROCESSED = "PROCESSED"
    PROCESSED_WITH_VALIDATION_ISSUES = "PROCESSED_WITH_VALIDATION_ISSUES"


class ConsolidationStatus(str, Enum):
    """Overall outcome for a batch of uploaded workbooks."""

    SUCCESS = "SUCCESS"
    PARTIAL_SUCCESS = "PARTIAL_SUCCESS"
    NO_SUCCESSFUL_FILES = "NO_SUCCESSFUL_FILES"


@dataclass(frozen=True)
class PreparedFile:
    """Read workbook data and schema state retained for later decisions."""

    file_index: int
    filename: str
    source_dataframe: pd.DataFrame | None
    schema_validation: SchemaValidationResult | None
    status: FileProcessingStatus
    error: str | None = None
    header_row: int | None = None
    header_candidates: tuple[int, ...] = ()
    automatic_project_rows: tuple[int, ...] = ()


@dataclass(frozen=True)
class PreparedBatchResult:
    """Ordered per-file preparation results awaiting optional mapping decisions."""

    files: tuple[PreparedFile, ...]


@dataclass(frozen=True)
class RowProvenance:
    """Source workbook and input-row location for one retained output row."""

    file_index: int
    filename: str
    source_row_position: int
    source_dataframe_index: Hashable


@dataclass(frozen=True)
class FileProcessingResult:
    """Final processing and validation outcome for one uploaded workbook."""

    file_index: int
    filename: str
    status: FileProcessingStatus
    schema_validation: SchemaValidationResult | None
    data_validation: DataValidationResult | None
    rows_read: int | None
    rows_cleaned: int | None
    error: str | None = None
    filter_audit: RecordFilterAudit | None = None

    @property
    def is_successful(self) -> bool:
        """Return whether the file contributed rows or a valid empty dataset."""
        return self.status in (
            FileProcessingStatus.PROCESSED,
            FileProcessingStatus.PROCESSED_WITH_VALIDATION_ISSUES,
        )


@dataclass(frozen=True)
class ConsolidationResult:
    """Batch DataFrame, per-file outcomes, findings, and duplicate counts."""

    dataframe: pd.DataFrame
    file_results: tuple[FileProcessingResult, ...]
    duplicates_detected: int
    duplicates_removed: int
    status: ConsolidationStatus
    row_provenance: tuple[RowProvenance, ...]
    filter_audit: RecordFilterAudit


def prepare_files(
    uploaded_files: Iterable[BinaryIO],
    *,
    header_row: int | None = None,
    text_columns: Sequence[str] = (),
) -> PreparedBatchResult:
    """Read and validate each upload while retaining data for approval decisions."""
    prepared_files: list[PreparedFile] = []
    for file_index, file_validation in enumerate(
        validate_uploaded_files(uploaded_files)
    ):
        if not file_validation.is_valid:
            prepared_files.append(
                PreparedFile(
                    file_index=file_index,
                    filename=file_validation.filename,
                    source_dataframe=None,
                    schema_validation=None,
                    status=FileProcessingStatus.FAILED,
                    error=file_validation.error,
                )
            )
            continue

        try:
            source_dataframe = read_rca_data(
                file_validation.file,
                header_row=header_row,
                text_columns=text_columns,
                filename=file_validation.filename,
            )
            schema_validation = validate_dataframe_schema(
                source_dataframe,
                workbook_name=file_validation.filename,
            )
        except AmbiguousHeaderRowError as exc:
            prepared_files.append(
                PreparedFile(
                    file_index=file_index,
                    filename=file_validation.filename,
                    source_dataframe=None,
                    schema_validation=None,
                    status=FileProcessingStatus.PENDING_HEADER_REVIEW,
                    error=str(exc),
                    header_candidates=exc.candidate_rows,
                )
            )
            continue
        except HeaderNotDetectedError as exc:
            prepared_files.append(
                PreparedFile(
                    file_index=file_index,
                    filename=file_validation.filename,
                    source_dataframe=None,
                    schema_validation=None,
                    status=FileProcessingStatus.INVALID_SCHEMA,
                    error=str(exc),
                )
            )
            continue
        except (ExcelReadError, ValueError) as exc:
            prepared_files.append(
                PreparedFile(
                    file_index=file_index,
                    filename=file_validation.filename,
                    source_dataframe=None,
                    schema_validation=None,
                    status=FileProcessingStatus.FAILED,
                    error=str(exc),
                )
            )
            continue

        if schema_validation.status is SchemaStatus.INVALID:
            status = FileProcessingStatus.INVALID_SCHEMA
        elif schema_validation.status is SchemaStatus.REVIEW_REQUIRED:
            status = FileProcessingStatus.PENDING_MAPPING_APPROVAL
        else:
            status = FileProcessingStatus.READY
        prepared_files.append(
            PreparedFile(
                file_index=file_index,
                filename=file_validation.filename,
                source_dataframe=source_dataframe,
                schema_validation=schema_validation,
                status=status,
                header_row=source_dataframe.attrs.get(HEADER_ROW_ATTR),
            )
        )

    return PreparedBatchResult(files=tuple(prepared_files))


def consolidate_prepared_files(
    prepared_batch: PreparedBatchResult,
    mapping_decisions_by_file: Mapping[int, Mapping[int, str | None]] | None = None,
    *,
    reporting_date: date | None = None,
) -> ConsolidationResult:
    """Finalize prepared workbooks, then deduplicate successful rows batch-wide."""
    if (
        reporting_date is None
        or isinstance(reporting_date, datetime)
        or not isinstance(reporting_date, date)
    ):
        raise ValueError("A reporting date must be selected before consolidation.")

    decisions_by_file = mapping_decisions_by_file or {}
    file_indexes = [prepared.file_index for prepared in prepared_batch.files]
    if len(file_indexes) != len(set(file_indexes)):
        raise ValueError("Prepared files must have unique file indexes.")
    unknown_file_indexes = set(decisions_by_file).difference(file_indexes)
    if unknown_file_indexes:
        raise ValueError(
            "Mapping decisions refer to unknown file indexes: "
            + ", ".join(str(index) for index in sorted(unknown_file_indexes))
        )

    file_results: list[FileProcessingResult] = []
    cleaned_dataframes: list[pd.DataFrame] = []
    provenance_by_output_index: dict[int, RowProvenance] = {}
    next_output_index = 0

    for prepared_file in prepared_batch.files:
        source_dataframe = prepared_file.source_dataframe
        schema_validation = prepared_file.schema_validation
        if source_dataframe is None or schema_validation is None:
            file_results.append(
                FileProcessingResult(
                    file_index=prepared_file.file_index,
                    filename=prepared_file.filename,
                    status=prepared_file.status,
                    schema_validation=schema_validation,
                    data_validation=None,
                    rows_read=None,
                    rows_cleaned=None,
                    error=prepared_file.error,
                )
            )
            continue

        if prepared_file.status is FileProcessingStatus.INVALID_SCHEMA:
            file_results.append(
                FileProcessingResult(
                    file_index=prepared_file.file_index,
                    filename=prepared_file.filename,
                    status=FileProcessingStatus.INVALID_SCHEMA,
                    schema_validation=schema_validation,
                    data_validation=None,
                    rows_read=len(source_dataframe),
                    rows_cleaned=None,
                    error=(
                        "Missing mandatory columns: "
                        + ", ".join(schema_validation.missing_columns)
                    ),
                )
            )
            continue

        decisions = decisions_by_file.get(prepared_file.file_index)
        if (
            prepared_file.status is FileProcessingStatus.PENDING_MAPPING_APPROVAL
            and not decisions
        ):
            file_results.append(
                FileProcessingResult(
                    file_index=prepared_file.file_index,
                    filename=prepared_file.filename,
                    status=FileProcessingStatus.PENDING_MAPPING_APPROVAL,
                    schema_validation=schema_validation,
                    data_validation=None,
                    rows_read=len(source_dataframe),
                    rows_cleaned=None,
                )
            )
            continue

        try:
            mapping_result: ColumnMappingResult = (
                schema_validation.mapping_result
            )
            if decisions:
                mapping_result = apply_mapping_decisions(mapping_result, decisions)
            resolved_schema = validate_dataframe_schema(
                source_dataframe,
                workbook_name=prepared_file.filename,
                mapping_result=mapping_result,
            )
            if resolved_schema.status is SchemaStatus.INVALID:
                file_results.append(
                    FileProcessingResult(
                        file_index=prepared_file.file_index,
                        filename=prepared_file.filename,
                        status=FileProcessingStatus.INVALID_SCHEMA,
                        schema_validation=resolved_schema,
                        data_validation=None,
                        rows_read=len(source_dataframe),
                        rows_cleaned=None,
                        error=(
                            "Missing mandatory columns: "
                            + ", ".join(resolved_schema.missing_columns)
                        ),
                    )
                )
                continue
            if resolved_schema.status is SchemaStatus.REVIEW_REQUIRED:
                file_results.append(
                    FileProcessingResult(
                        file_index=prepared_file.file_index,
                        filename=prepared_file.filename,
                        status=FileProcessingStatus.PENDING_MAPPING_APPROVAL,
                        schema_validation=resolved_schema,
                        data_validation=None,
                        rows_read=len(source_dataframe),
                        rows_cleaned=None,
                    )
                )
                continue

            mapped_dataframe = apply_approved_mappings(
                source_dataframe,
                mapping_result,
            )
            filter_result = filter_rca_records(
                mapped_dataframe,
                reporting_date,
            )
            cleaned_dataframe = clean_dataframe(filter_result.dataframe)
            data_validation = validate_cleaned_dataframe(cleaned_dataframe)
        except ValueError as exc:
            file_results.append(
                FileProcessingResult(
                    file_index=prepared_file.file_index,
                    filename=prepared_file.filename,
                    status=FileProcessingStatus.FAILED,
                    schema_validation=schema_validation,
                    data_validation=None,
                    rows_read=len(source_dataframe),
                    rows_cleaned=None,
                    error=str(exc),
                )
            )
            continue

        has_validation_issues = (
            bool(data_validation.blank_cells)
            or bool(data_validation.unsupported_dates)
            or data_validation.requires_review
        )
        file_results.append(
            FileProcessingResult(
                file_index=prepared_file.file_index,
                filename=prepared_file.filename,
                status=(
                    FileProcessingStatus.PROCESSED_WITH_VALIDATION_ISSUES
                    if has_validation_issues
                    else FileProcessingStatus.PROCESSED
                ),
                schema_validation=resolved_schema,
                data_validation=data_validation,
                rows_read=len(source_dataframe),
                rows_cleaned=len(cleaned_dataframe),
                filter_audit=filter_result.audit,
            )
        )

        original_indexes = list(cleaned_dataframe.index)
        source_positions = {
            source_index: position
            for position, source_index in enumerate(source_dataframe.index)
        }
        row_count = len(cleaned_dataframe)
        cleaned_dataframe = cleaned_dataframe.copy(deep=True)
        cleaned_dataframe.index = pd.RangeIndex(
            next_output_index,
            next_output_index + row_count,
        )
        for row_position, source_index in enumerate(original_indexes):
            output_index = next_output_index + row_position
            provenance_by_output_index[output_index] = RowProvenance(
                file_index=prepared_file.file_index,
                filename=prepared_file.filename,
                source_row_position=source_positions[source_index],
                source_dataframe_index=source_index,
            )
        next_output_index += row_count
        cleaned_dataframes.append(cleaned_dataframe)

    deduplication = consolidate_dataframes(cleaned_dataframes)
    retained_indexes = list(deduplication.deduplicated_dataframe.index)
    row_provenance = tuple(
        provenance_by_output_index[index] for index in retained_indexes
    )
    consolidated_dataframe = deduplication.deduplicated_dataframe.reset_index(
        drop=True
    )
    retained_counts = Counter(
        provenance.file_index for provenance in row_provenance
    )
    for result_index, file_result in enumerate(file_results):
        audit = file_result.filter_audit
        if audit is None:
            continue
        records_after_duplicate_removal = retained_counts[file_result.file_index]
        updated_audit = replace(
            audit,
            records_after_duplicate_removal=records_after_duplicate_removal,
            duplicates_removed=(
                audit.records_after_outage_filter
                - records_after_duplicate_removal
            ),
        )
        file_results[result_index] = replace(
            file_result,
            filter_audit=updated_audit,
        )
    batch_filter_audit = aggregate_filter_audits(
        tuple(
            file_result.filter_audit
            for file_result in file_results
            if file_result.filter_audit is not None
        ),
        reporting_date,
    )

    successful_count = sum(result.is_successful for result in file_results)
    if successful_count == 0:
        status = ConsolidationStatus.NO_SUCCESSFUL_FILES
    elif successful_count < len(file_results):
        status = ConsolidationStatus.PARTIAL_SUCCESS
    else:
        status = ConsolidationStatus.SUCCESS

    return ConsolidationResult(
        dataframe=consolidated_dataframe,
        file_results=tuple(file_results),
        duplicates_detected=deduplication.duplicates_detected,
        duplicates_removed=deduplication.duplicates_removed,
        status=status,
        row_provenance=row_provenance,
        filter_audit=batch_filter_audit,
    )