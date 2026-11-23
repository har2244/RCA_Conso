"""Run the existing RCA consolidation service against real Excel workbooks."""

import argparse
from collections import Counter
from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path
import sys
from typing import Callable, Mapping, Sequence, TextIO, TypeVar


_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_ConfigValue = TypeVar("_ConfigValue", int, str)
for _import_path in (_PROJECT_ROOT, _PROJECT_ROOT / "src"):
    if str(_import_path) not in sys.path:
        sys.path.insert(0, str(_import_path))

from config.column_schema import MANDATORY_COLUMNS
from rca_consolidator.processing.column_mapper import (
    apply_approved_mappings,
    apply_mapping_decisions,
)
from rca_consolidator.services.consolidation_service import (
    FileProcessingResult,
    FileProcessingStatus,
    PreparedBatchResult,
    PreparedFile,
    consolidate_prepared_files,
    prepare_files,
)
from rca_consolidator.validation.schema_validator import (
    SchemaStatus,
    validate_dataframe_schema,
)
from rca_consolidator.validation.project_validator import (
    APPROVED_PROJECT_VALUES,
    ProjectIdentityStatus,
    apply_circle_project_assignment,
    apply_project_assignment,
    validate_project_identity,
)


@dataclass(frozen=True)
class _ProjectIdentity:
    status: str
    project: str | None = None
    findings: tuple[str, ...] = ()
    blocked: bool = False


class _NamedWorkbook:
    """Expose a path-backed binary stream with the filename expected by ingestion."""

    def __init__(self, path: Path) -> None:
        self.name = path.name
        self._stream = path.open("rb")

    def read(self, size: int = -1) -> bytes:
        return self._stream.read(size)

    def seek(self, offset: int, whence: int = 0) -> int:
        return self._stream.seek(offset, whence)

    def tell(self) -> int:
        return self._stream.tell()

    def close(self) -> None:
        self._stream.close()

    def __getattr__(self, attribute: str) -> object:
        return getattr(self._stream, attribute)


def _normalized_workbook_path(path: str | Path) -> str:
    return str(Path(path).resolve())


def _normalize_path_mapping(
    paths: Mapping[str, _ConfigValue],
    setting_name: str,
) -> dict[str, _ConfigValue]:
    normalized: dict[str, _ConfigValue] = {}
    for path, value in paths.items():
        resolved_path = _normalized_workbook_path(path)
        if resolved_path in normalized:
            raise ValueError(
                f"{setting_name} was specified more than once for "
                f"{resolved_path!r}."
            )
        normalized[resolved_path] = value
    return normalized


def _prompt_for_decision(
    source_name: object,
    source_index: int,
    suggested_target: str | None,
    candidates: tuple[str, ...],
    input_fn: Callable[[str], str],
    output: TextIO,
) -> str | None:
    print(
        f"Source column {source_index}: {source_name!r}",
        file=output,
    )
    print(
        f"Suggested standard column: {suggested_target or 'multiple candidates'}",
        file=output,
    )
    for candidate_index, candidate in enumerate(candidates, start=1):
        print(f"  {candidate_index}. {candidate}", file=output)
    print(
        "Enter a candidate number to approve it, or 'r' to reject:",
        file=output,
    )

    while True:
        answer = input_fn("").strip().casefold()
        if answer == "r":
            return None
        if answer.isdigit():
            candidate_index = int(answer)
            if 1 <= candidate_index <= len(candidates):
                return candidates[candidate_index - 1]
        print(
            f"Choose a number from 1 to {len(candidates)}, or 'r'.",
            file=output,
        )


def _collect_mapping_decisions(
    prepared_batch: PreparedBatchResult,
    input_fn: Callable[[str], str],
    output: TextIO,
) -> dict[int, dict[int, str | None]]:
    decisions_by_file: dict[int, dict[int, str | None]] = {}
    for prepared_file in prepared_batch.files:
        if (
            prepared_file.status
            is not FileProcessingStatus.PENDING_MAPPING_APPROVAL
            or prepared_file.schema_validation is None
        ):
            continue

        suggestions = prepared_file.schema_validation.mapping_result.suggestions
        file_decisions: dict[int, str | None] = {}
        for mapping in suggestions:
            if mapping.source_index is None or not mapping.candidate_targets:
                continue
            decision = _prompt_for_decision(
                source_name=mapping.original_column,
                source_index=mapping.source_index,
                suggested_target=mapping.target_column,
                candidates=mapping.candidate_targets,
                input_fn=input_fn,
                output=output,
            )
            file_decisions[mapping.source_index] = decision
        if file_decisions:
            decisions_by_file[prepared_file.file_index] = file_decisions
    return decisions_by_file


def _status_for_schema(schema_status: SchemaStatus) -> FileProcessingStatus:
    if schema_status is SchemaStatus.INVALID:
        return FileProcessingStatus.INVALID_SCHEMA
    if schema_status is SchemaStatus.REVIEW_REQUIRED:
        return FileProcessingStatus.PENDING_MAPPING_APPROVAL
    return FileProcessingStatus.READY


def _prompt_for_project_assignment(
    filename: str,
    input_fn: Callable[[str], str],
    output: TextIO,
) -> str | None:
    print(
        f"Project column is missing or contains blank values in "
        f"{filename!r}. Assign {' or '.join(APPROVED_PROJECT_VALUES)}, or "
        "enter 'r' to leave unresolved:",
        file=output,
    )
    while True:
        answer = input_fn("").strip()
        if not answer or answer.casefold() == "r":
            return None
        if answer in APPROVED_PROJECT_VALUES:
            return answer
        print(
            "Enter exactly 'LWE', '4G Saturation', or 'r'.",
            file=output,
        )


def _resolve_project_identity(
    prepared_file: PreparedFile,
    mapping_decisions: Mapping[int, str | None],
    project_assignment: str | None,
    input_fn: Callable[[str], str],
    output: TextIO,
) -> tuple[PreparedFile, _ProjectIdentity]:
    dataframe = prepared_file.source_dataframe
    schema = prepared_file.schema_validation
    if dataframe is None or schema is None:
        return prepared_file, _ProjectIdentity("UNAVAILABLE")

    mapping_result = schema.mapping_result
    try:
        if mapping_decisions:
            mapping_result = apply_mapping_decisions(
                mapping_result,
                mapping_decisions,
            )
        resolved_schema = validate_dataframe_schema(
            dataframe,
            workbook_name=prepared_file.filename,
            mapping_result=mapping_result,
        )
        apply_approved_mappings(dataframe, mapping_result)
    except ValueError:
        return prepared_file, _ProjectIdentity(
            "PROJECT_MAPPING_UNRESOLVED",
            findings=("Project source mapping could not be resolved.",),
            blocked=True,
        )
    prepared_file = replace(
        prepared_file,
        schema_validation=resolved_schema,
        status=_status_for_schema(resolved_schema.status),
    )

    automatic_assignment = apply_circle_project_assignment(
        dataframe,
        mapping_result,
    )
    automatic_assignment_note: str | None = None
    if automatic_assignment.assigned_row_positions:
        dataframe = automatic_assignment.dataframe
        updated_schema = validate_dataframe_schema(
            dataframe,
            workbook_name=prepared_file.filename,
        )
        if mapping_decisions:
            updated_mapping_result = apply_mapping_decisions(
                updated_schema.mapping_result,
                mapping_decisions,
            )
            updated_schema = validate_dataframe_schema(
                dataframe,
                workbook_name=prepared_file.filename,
                mapping_result=updated_mapping_result,
            )
        mapping_result = updated_schema.mapping_result
        prepared_file = replace(
            prepared_file,
            source_dataframe=dataframe,
            schema_validation=updated_schema,
            status=_status_for_schema(updated_schema.status),
            automatic_project_rows=automatic_assignment.assigned_row_positions,
        )
        automatic_assignment_note = (
            "Project automatically assigned as '4G Saturation' from Circle "
            f"at data rows {list(automatic_assignment.assigned_row_positions)}."
        )
        apply_approved_mappings(dataframe, mapping_result)

    identity_result = validate_project_identity(dataframe, mapping_result)
    assignment_note: str | None = None
    missing_project_column = (
        identity_result.status is ProjectIdentityStatus.MISSING_COLUMN
    )
    if identity_result.status in (
        ProjectIdentityStatus.MISSING_COLUMN,
        ProjectIdentityStatus.MISSING_VALUES,
    ):
        assignment = project_assignment
        if (
            identity_result.status is ProjectIdentityStatus.MISSING_VALUES
            and assignment is None
        ):
            assignment = _prompt_for_project_assignment(
                prepared_file.filename,
                input_fn,
                output,
            )
            if assignment is None:
                return prepared_file, _ProjectIdentity(
                    "INVALID_PROJECT_VALUES",
                    findings=identity_result.findings,
                    blocked=True,
                )
        if assignment is not None and assignment not in APPROVED_PROJECT_VALUES:
            return prepared_file, _ProjectIdentity(
                "MISSING_PROJECT",
                findings=(
                    f"Unsupported project assignment {assignment!r}; "
                    f"choose {APPROVED_PROJECT_VALUES}.",
                ),
                blocked=True,
            )
        if assignment is None:
            assignment = _prompt_for_project_assignment(
                prepared_file.filename,
                input_fn,
                output,
            )
        if assignment is None:
            return prepared_file, _ProjectIdentity(
                "MISSING_PROJECT",
                findings=("No project assignment was supplied.",),
                blocked=True,
            )

        dataframe = apply_project_assignment(
            dataframe,
            mapping_result,
            assignment,
        )
        updated_schema = validate_dataframe_schema(
            dataframe,
            workbook_name=prepared_file.filename,
        )
        if mapping_decisions:
            updated_mapping_result = apply_mapping_decisions(
                updated_schema.mapping_result,
                mapping_decisions,
            )
            updated_schema = validate_dataframe_schema(
                dataframe,
                workbook_name=prepared_file.filename,
                mapping_result=updated_mapping_result,
            )
        prepared_file = replace(
            prepared_file,
            source_dataframe=dataframe,
            schema_validation=updated_schema,
            status=_status_for_schema(updated_schema.status),
        )
        assignment_note = (
            f"MISSING_PROJECT resolved by explicit assignment {assignment!r}."
            if missing_project_column
            else f"Missing Project values assigned as {assignment!r}."
        )
        mapping_result = updated_schema.mapping_result
        apply_approved_mappings(dataframe, mapping_result)
        identity_result = validate_project_identity(dataframe, mapping_result)
    elif project_assignment is not None and identity_result.status in (
        ProjectIdentityStatus.VALID,
        ProjectIdentityStatus.NO_RECORDS,
    ):
        assignment_note = (
            "Assignment was not applied because Project already exists; "
            "source values were preserved."
        )

    if identity_result.status in (
        ProjectIdentityStatus.VALID,
        ProjectIdentityStatus.NO_RECORDS,
    ):
        is_assigned = (
            automatic_assignment_note is not None
            or (
                assignment_note is not None
                and assignment_note.startswith(
                    ("MISSING_PROJECT", "Missing Project values assigned")
                )
            )
        )
        return prepared_file, _ProjectIdentity(
            "ASSIGNED"
            if is_assigned
            else (
                "CONFIRMED_EMPTY"
                if identity_result.status is ProjectIdentityStatus.NO_RECORDS
                else "CONFIRMED"
            ),
            project=identity_result.project,
            findings=(
                *identity_result.findings,
                *((automatic_assignment_note,) if automatic_assignment_note else ()),
                *((assignment_note,) if assignment_note else ()),
            ),
        )

    project_statuses = {
        ProjectIdentityStatus.MISSING_COLUMN: "MISSING_PROJECT",
        ProjectIdentityStatus.MISSING_VALUES: "INVALID_PROJECT_VALUES",
        ProjectIdentityStatus.INVALID_VALUES: "INVALID_PROJECT_VALUES",
        ProjectIdentityStatus.INCONSISTENT_VALUES: "INVALID_PROJECT_VALUES",
        ProjectIdentityStatus.CONFLICTING_COLUMNS: "PROJECT_MAPPING_UNRESOLVED",
        ProjectIdentityStatus.MAPPING_REVIEW_REQUIRED: "PROJECT_MAPPING_UNRESOLVED",
    }
    return prepared_file, _ProjectIdentity(
        status=project_statuses[identity_result.status],
        findings=(
            *identity_result.findings,
            *((assignment_note,) if assignment_note else ()),
        ),
        blocked=True,
    )


def _display_schema_findings(
    label: str,
    prepared_file: PreparedFile | None,
    file_result: FileProcessingResult,
    output: TextIO,
) -> None:
    if prepared_file is not None:
        if prepared_file.header_row is not None:
            print(
                f"Excel header row: {prepared_file.header_row}",
                file=output,
            )
        elif prepared_file.header_candidates:
            print(
                "Header row requires manual review; candidates: "
                + ", ".join(str(row) for row in prepared_file.header_candidates),
                file=output,
            )
    schema = (
        file_result.schema_validation
        if file_result.schema_validation is not None
        else prepared_file.schema_validation if prepared_file is not None else None
    )
    if schema is None:
        print(f"{label}: unavailable", file=output)
        return

    print(f"{label}: {schema.status.value}", file=output)
    if schema.missing_columns:
        print(f"  Missing mandatory columns: {schema.missing_columns}", file=output)
    if schema.unexpected_columns:
        print(f"  Extra/unmapped columns: {schema.unexpected_columns}", file=output)
    if schema.duplicate_source_columns:
        print(
            f"  Duplicate source headers: {schema.duplicate_source_columns}",
            file=output,
        )
    if schema.conflicting_targets:
        print(f"  Conflicting targets: {schema.conflicting_targets}", file=output)

    for suggestion in schema.mapping_result.suggestions:
        print(
            f"  Mapping suggestion at source index {suggestion.source_index}: "
            f"{suggestion.original_column!r} -> "
            f"{suggestion.target_column or 'ambiguous'}; "
            f"candidates={suggestion.candidate_targets}",
            file=output,
        )


def _display_file_result(
    file_result: FileProcessingResult,
    prepared_file: PreparedFile | None,
    retained_count: int,
    output: TextIO,
) -> None:
    print(f"\nFilename: {file_result.filename}", file=output)
    print(f"Processing status: {file_result.status.value}", file=output)
    input_rows = (
        "unavailable" if file_result.rows_read is None else file_result.rows_read
    )
    print(f"Input rows: {input_rows}", file=output)
    print(f"Retained rows: {retained_count}", file=output)
    audit = file_result.filter_audit
    if audit is not None:
        print("Filtering audit:", file=output)
        print(
            f"  Reporting date: {audit.reporting_date.isoformat()}",
            file=output,
        )
        print(
            f"  Matching reporting date: "
            f"{audit.records_matching_reporting_date}",
            file=output,
        )
        print(
            f"  After O&M filter: {audit.records_after_om_filter}",
            file=output,
        )
        print(
            f"  After outage filter: {audit.records_after_outage_filter}",
            file=output,
        )
        print(
            f"  Excluded by date/O&M/outage: "
            f"{audit.excluded_by_reporting_date}/"
            f"{audit.excluded_by_om_filter}/"
            f"{audit.excluded_by_outage_filter}",
            file=output,
        )
        print(
            f"  After duplicate removal: "
            f"{audit.records_after_duplicate_removal}",
            file=output,
        )
        print(
            "  Blank/invalid Date: "
            f"{audit.blank_date_values}/{audit.invalid_date_values}",
            file=output,
        )
        print(
            "  Blank/invalid O&M Start: "
            f"{audit.blank_om_values}/{audit.invalid_om_values}",
            file=output,
        )
        print(
            "  Blank/invalid Outage Min.: "
            f"{audit.blank_outage_values}/{audit.invalid_outage_values}",
            file=output,
        )

    _display_schema_findings(
        "Schema validation",
        prepared_file,
        file_result,
        output,
    )

    validation = file_result.data_validation
    if validation is None:
        print("Data validation findings: unavailable", file=output)
    else:
        print("Data validation findings:", file=output)
        for issue in validation.blank_cells:
            print(
                f"  Blank {issue.column} at data row {issue.row_position + 1}",
                file=output,
            )
        for issue in validation.unsupported_dates:
            print(
                f"  Unsupported date at data row {issue.row_position + 1}: "
                f"{issue.value!r}",
                file=output,
            )
        for finding in validation.site_id_format_findings:
            print(
                f"  Site ID format at {finding.cell_coordinate}: "
                f"{finding.number_format!r}, raw value={finding.raw_value!r}; "
                f"{finding.reason}",
                file=output,
            )
        if not (
            validation.blank_cells
            or validation.unsupported_dates
            or validation.site_id_format_findings
        ):
            print("  None", file=output)

    if file_result.error:
        print(f"Error: {file_result.error}", file=output)
    elif file_result.status is FileProcessingStatus.PENDING_MAPPING_APPROVAL:
        print(
            "Error: mapping or schema issues remain unresolved.",
            file=output,
        )


def _display_project_identity(
    identity: _ProjectIdentity,
    output: TextIO,
) -> None:
    suffix = f" ({identity.project})" if identity.project else ""
    print(f"Project identity: {identity.status}{suffix}", file=output)
    for finding in identity.findings:
        print(f"  Project finding: {finding}", file=output)


def _display_blocked_project_file(
    workbook_path: Path,
    prepared_file: PreparedFile,
    identity: _ProjectIdentity,
    output: TextIO,
) -> None:
    print(f"\nFilename: {workbook_path.name}", file=output)
    print(f"Processing status: {identity.status}", file=output)
    if prepared_file.header_row is not None:
        print(f"Excel header row: {prepared_file.header_row}", file=output)
    rows_read = (
        len(prepared_file.source_dataframe)
        if prepared_file.source_dataframe is not None
        else "unavailable"
    )
    print(f"Input rows: {rows_read}", file=output)
    print("Retained rows: 0", file=output)
    _display_project_identity(identity, output)
    if prepared_file.schema_validation is not None:
        schema = prepared_file.schema_validation
        print(f"Schema validation: {schema.status.value}", file=output)
        if schema.missing_columns:
            print(
                f"  Missing mandatory columns: {schema.missing_columns}",
                file=output,
            )
    print("Error: Project identity is unresolved; workbook was excluded.", file=output)


def run_real_workbook_test(
    workbook_paths: Sequence[Path],
    *,
    reporting_date: date,
    header_rows_by_path: Mapping[str, int] | None = None,
    project_assignments_by_path: Mapping[str, str] | None = None,
    input_fn: Callable[[str], str] | None = None,
    output: TextIO | None = None,
) -> int:
    """Run the service and print a per-file and batch report."""
    input_fn = input if input_fn is None else input_fn
    output = sys.stdout if output is None else output
    try:
        normalized_header_rows = _normalize_path_mapping(
            header_rows_by_path or {},
            "Header row",
        )
        normalized_project_assignments = _normalize_path_mapping(
            project_assignments_by_path or {},
            "Project assignment",
        )
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"Invalid workbook configuration path: {exc}", file=output)
        return 2
    opened_workbooks: list[_NamedWorkbook] = []
    opened_input_positions: list[int] = []
    preflight_errors: dict[int, str] = {}

    try:
        provided_paths = {
            _normalized_workbook_path(path) for path in workbook_paths
        }
        unknown_config_paths = (
            set(normalized_header_rows) | set(normalized_project_assignments)
        ).difference(provided_paths)
        if unknown_config_paths:
            print(
                "Configuration refers to workbook path(s) not provided: "
                + ", ".join(sorted(unknown_config_paths)),
                file=output,
            )
            return 2
        invalid_header_rows = {
            path: row
            for path, row in normalized_header_rows.items()
            if not isinstance(row, int) or row < 1
        }
        if invalid_header_rows:
            print(
                "Header rows must be positive one-based integers: "
                + ", ".join(
                    f"{path}={row}"
                    for path, row in sorted(invalid_header_rows.items())
                ),
                file=output,
            )
            return 2
        invalid_project_assignments = {
            path: project
            for path, project in normalized_project_assignments.items()
            if project not in APPROVED_PROJECT_VALUES
        }
        if invalid_project_assignments:
            print(
                "Project assignments must use an approved value "
                f"{APPROVED_PROJECT_VALUES}: "
                + ", ".join(
                    f"{path}={project!r}"
                    for path, project in sorted(
                        invalid_project_assignments.items()
                    )
                ),
                file=output,
            )
            return 2

        for input_position, workbook_path in enumerate(workbook_paths):
            path = Path(workbook_path)
            try:
                if not path.exists():
                    preflight_errors[input_position] = "File not found."
                elif not path.is_file():
                    preflight_errors[input_position] = "Path is not a file."
                else:
                    opened_workbooks.append(_NamedWorkbook(path))
                    opened_input_positions.append(input_position)
            except OSError as exc:
                preflight_errors[input_position] = f"Could not open file: {exc}"

        prepared_files: list[PreparedFile] = []
        for service_index, (workbook, input_position) in enumerate(
            zip(opened_workbooks, opened_input_positions)
        ):
            workbook_path = _normalized_workbook_path(
                workbook_paths[input_position]
            )
            header_row = normalized_header_rows.get(workbook_path)
            if header_row is None:
                prepared_file = prepare_files([workbook]).files[0]
            else:
                prepared_file = prepare_files(
                    [workbook],
                    header_row=header_row,
                ).files[0]
            prepared_file = replace(prepared_file, file_index=service_index)
            prepared_files.append(prepared_file)

        prepared_batch = PreparedBatchResult(files=tuple(prepared_files))
        try:
            mapping_decisions = _collect_mapping_decisions(
                prepared_batch,
                input_fn,
                output,
            )
        except (EOFError, KeyboardInterrupt):
            print(
                "\nMapping approval was interrupted; consolidation was not run.",
                file=output,
            )
            return 2

        identity_by_input: dict[int, _ProjectIdentity] = {}
        blocked_by_input: dict[int, tuple[PreparedFile, _ProjectIdentity]] = {}
        eligible_files: list[PreparedFile] = []
        eligible_input_positions: list[int] = []
        try:
            for prepared_file in prepared_batch.files:
                input_position = opened_input_positions[prepared_file.file_index]
                workbook_path = _normalized_workbook_path(
                    workbook_paths[input_position]
                )
                updated_file, identity = _resolve_project_identity(
                    prepared_file,
                    mapping_decisions.get(prepared_file.file_index, {}),
                    normalized_project_assignments.get(workbook_path),
                    input_fn,
                    output,
                )
                identity_by_input[input_position] = identity
                if identity.blocked:
                    blocked_by_input[input_position] = (updated_file, identity)
                    continue

                new_file_index = len(eligible_files)
                eligible_files.append(
                    replace(updated_file, file_index=new_file_index)
                )
                eligible_input_positions.append(input_position)
        except (EOFError, KeyboardInterrupt):
            print(
                "\nProject assignment was interrupted; consolidation was not run.",
                file=output,
            )
            return 2

        eligible_batch = PreparedBatchResult(files=tuple(eligible_files))
        result = consolidate_prepared_files(
            eligible_batch,
            reporting_date=reporting_date,
        )
        prepared_by_index = {
            prepared.file_index: prepared for prepared in eligible_batch.files
        }
        service_result_by_input: dict[int, FileProcessingResult] = {}
        for file_result in result.file_results:
            input_position = eligible_input_positions[file_result.file_index]
            service_result_by_input[input_position] = file_result

        retained_by_file = Counter(
            provenance.file_index for provenance in result.row_provenance
        )
        print("RCA Consolidation Test Report", file=output)
        for input_position, workbook_path in enumerate(workbook_paths):
            file_result = service_result_by_input.get(input_position)
            if file_result is None:
                blocked = blocked_by_input.get(input_position)
                if blocked is not None:
                    _display_blocked_project_file(
                        Path(workbook_path),
                        blocked[0],
                        blocked[1],
                        output,
                    )
                    continue
                print(f"\nFilename: {Path(workbook_path).name}", file=output)
                print("Processing status: FAILED", file=output)
                print("Input rows: unavailable", file=output)
                print("Retained rows: 0", file=output)
                print(f"Error: {preflight_errors[input_position]}", file=output)
                continue

            prepared_file = prepared_by_index[file_result.file_index]
            _display_file_result(
                file_result,
                prepared_file,
                retained_by_file[file_result.file_index],
                output,
            )
            identity = identity_by_input.get(input_position)
            if identity is not None:
                _display_project_identity(identity, output)

        total_input_records = sum(
            file_result.rows_read or 0 for file_result in result.file_results
        )
        total_input_records += sum(
            len(prepared.source_dataframe)
            for prepared, _ in blocked_by_input.values()
            if prepared.source_dataframe is not None
        )
        successful_files = sum(
            file_result.is_successful for file_result in result.file_results
        )
        print("\nBatch statistics", file=output)
        print(
            f"Reporting date: {result.filter_audit.reporting_date.isoformat()}",
            file=output,
        )
        total_failed_files = (
            len(preflight_errors)
            + len(blocked_by_input)
            + sum(
                not file_result.is_successful
                for file_result in result.file_results
            )
        )
        if successful_files == 0:
            batch_status = "NO_SUCCESSFUL_FILES"
        elif total_failed_files:
            batch_status = "PARTIAL_SUCCESS"
        else:
            batch_status = "SUCCESS"
        print(f"Batch status: {batch_status}", file=output)
        print(f"Successfully processed files: {successful_files}", file=output)
        print(f"Total input records: {total_input_records}", file=output)
        print(
            f"Filtering totals (original={result.filter_audit.original_records}): "
            f"matching date={result.filter_audit.records_matching_reporting_date}, "
            f"after O&M={result.filter_audit.records_after_om_filter}, "
            f"after outage={result.filter_audit.records_after_outage_filter}, "
            f"after duplicates="
            f"{result.filter_audit.records_after_duplicate_removal}",
            file=output,
        )
        print(
            "Filter exclusions (date/O&M/outage): "
            f"{result.filter_audit.excluded_by_reporting_date}/"
            f"{result.filter_audit.excluded_by_om_filter}/"
            f"{result.filter_audit.excluded_by_outage_filter}",
            file=output,
        )
        print(
            "Blank/invalid Date, O&M Start, Outage Min.: "
            f"{result.filter_audit.blank_date_values}/"
            f"{result.filter_audit.invalid_date_values}, "
            f"{result.filter_audit.blank_om_values}/"
            f"{result.filter_audit.invalid_om_values}, "
            f"{result.filter_audit.blank_outage_values}/"
            f"{result.filter_audit.invalid_outage_values}",
            file=output,
        )
        print(f"Duplicate records removed: {result.duplicates_removed}", file=output)
        print(f"Final consolidated records: {len(result.dataframe)}", file=output)
        if "Project" in result.dataframe:
            project_counts = result.dataframe["Project"].value_counts()
            print(
                "Project counts: "
                + ", ".join(
                    f"{project}={int(project_counts.get(project, 0))}"
                    for project in APPROVED_PROJECT_VALUES
                ),
                file=output,
            )
        print(
            "Final schema: " + ", ".join(MANDATORY_COLUMNS),
            file=output,
        )

        all_files_succeeded = (
            not preflight_errors
            and not blocked_by_input
            and len(result.file_results)
            + len(blocked_by_input)
            + len(preflight_errors)
            == len(workbook_paths)
            and all(file_result.is_successful for file_result in result.file_results)
        )
        return 0 if all_files_succeeded else 1
    finally:
        for workbook in opened_workbooks:
            workbook.close()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run the existing RCA consolidation service against one or more "
            ".xlsx or .xlsm workbooks."
        )
    )
    parser.add_argument(
        "workbooks",
        nargs="+",
        type=Path,
        help="Paths to Excel workbooks to process.",
    )
    parser.add_argument(
        "--reporting-date",
        required=True,
        type=date.fromisoformat,
        metavar="YYYY-MM-DD",
        help="Reporting date to retain in every workbook.",
    )
    parser.add_argument(
        "--header-row",
        action="append",
        default=[],
        metavar="PATH=ROW",
        help="One-based Excel header row for a specific path; repeat as needed.",
    )
    parser.add_argument(
        "--project-assignment",
        action="append",
        default=[],
        metavar="PATH=PROJECT",
        help=(
            "Assign missing Project values for one path to LWE or "
            "4G Saturation; repeat as needed."
        ),
    )
    parser.add_argument(
        "--metadata-override",
        action="append",
        default=[],
        metavar="PATH=Project=VALUE",
        help=argparse.SUPPRESS,
    )
    args = parser.parse_args(argv)

    header_rows: dict[str, int] = {}
    for specification in args.header_row:
        path, separator, row_text = specification.partition("=")
        if not separator or not path or not row_text:
            parser.error("--header-row must use PATH=ROW.")
        try:
            normalized_path = _normalized_workbook_path(path)
        except (OSError, RuntimeError, ValueError) as exc:
            parser.error(f"Invalid path in --header-row: {exc}")
        if normalized_path in header_rows:
            parser.error(
                f"Header row was specified more than once for {path!r}."
            )
        try:
            header_rows[normalized_path] = int(row_text)
        except ValueError:
            parser.error(f"Header row for {path!r} must be an integer.")

    project_assignments: dict[str, str] = {}
    assignment_specs = [
        (specification, False) for specification in args.project_assignment
    ] + [(specification, True) for specification in args.metadata_override]
    for specification, is_legacy in assignment_specs:
        if is_legacy:
            path, separator, remainder = specification.partition("=")
            column, value_separator, value = remainder.partition("=")
            if not separator or not path or not value_separator or not value:
                parser.error("--metadata-override must use PATH=Project=VALUE.")
            if column != "Project":
                parser.error("Only a Project assignment is supported.")
        else:
            path, separator, value = specification.partition("=")
            if not separator or not path or not value:
                parser.error("--project-assignment must use PATH=PROJECT.")
        if value not in APPROVED_PROJECT_VALUES:
            parser.error(
                f"Project assignment must be one of {APPROVED_PROJECT_VALUES}."
            )
        try:
            normalized_path = _normalized_workbook_path(path)
        except (OSError, RuntimeError, ValueError) as exc:
            parser.error(f"Invalid project assignment path: {exc}")
        if normalized_path in project_assignments:
            parser.error(
                f"Project assignment was specified more than once for {path!r}."
            )
        project_assignments[normalized_path] = value

    return run_real_workbook_test(
        args.workbooks,
        reporting_date=args.reporting_date,
        header_rows_by_path=header_rows,
        project_assignments_by_path=project_assignments,
    )


if __name__ == "__main__":
    raise SystemExit(main())
