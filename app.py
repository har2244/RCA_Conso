"""Streamlit workbook configuration, validation, and consolidation UI."""

import hashlib
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parent
SOURCE_ROOT = PROJECT_ROOT / "src"
source_root = str(SOURCE_ROOT)
while source_root in sys.path:
    sys.path.remove(source_root)
sys.path.insert(0, source_root)

from rca_consolidator.services.consolidation_service import (
    ConsolidationResult,
    FileProcessingStatus,
    PreparedBatchResult,
    PreparedFile,
    consolidate_prepared_files,
    prepare_files,
)
from rca_consolidator.processing.column_mapper import apply_approved_mappings
from rca_consolidator.export.excel_writer import write_rca_workbook
from rca_consolidator.validation.project_validator import (
    APPROVED_PROJECT_VALUES,
    ProjectIdentityResult,
    ProjectIdentityStatus,
    apply_circle_project_assignment,
    apply_project_assignment,
    apply_project_value_corrections,
    suggest_project_value_corrections,
    validate_project_identity,
)
from rca_consolidator.validation.bucket_validator import (
    BucketValidationResult,
    validate_bucket_combinations,
)
from rca_consolidator.validation.schema_validator import (
    SchemaStatus,
    validate_dataframe_schema,
)


def _upload_signature(uploaded_files: list[Any]) -> tuple[tuple[str, str], ...]:
    """Identify the exact upload set without changing its stream positions."""
    return tuple(
        (
            uploaded_file.name,
            hashlib.sha256(uploaded_file.getvalue()).hexdigest(),
        )
        for uploaded_file in uploaded_files
    )


def _prepare_uploaded_files(
    uploaded_files: list[Any],
    manual_header_rows: dict[str, int],
    upload_key: str,
) -> PreparedBatchResult:
    prepared_files: list[PreparedFile] = []
    for file_index, uploaded_file in enumerate(uploaded_files):
        manual_header_row = manual_header_rows.get(
            f"{upload_key}-{file_index}"
        )
        if manual_header_row is None:
            single_file_batch = prepare_files([uploaded_file])
        else:
            single_file_batch = prepare_files(
                [uploaded_file],
                header_row=manual_header_row,
            )
        if len(single_file_batch.files) != 1:
            raise RuntimeError(
                f"Expected one preparation result for {uploaded_file.name!r}."
            )
        prepared_files.append(
            replace(single_file_batch.files[0], file_index=file_index)
        )
    return PreparedBatchResult(files=tuple(prepared_files))


def _project_result(prepared_file: PreparedFile) -> ProjectIdentityResult | None:
    if (
        prepared_file.source_dataframe is None
        or prepared_file.schema_validation is None
    ):
        return None
    return validate_project_identity(
        prepared_file.source_dataframe,
        prepared_file.schema_validation.mapping_result,
    )


def _with_circle_project_assignment(
    prepared_file: PreparedFile,
) -> PreparedFile:
    if (
        prepared_file.source_dataframe is None
        or prepared_file.schema_validation is None
    ):
        return prepared_file

    assignment = apply_circle_project_assignment(
        prepared_file.source_dataframe,
        prepared_file.schema_validation.mapping_result,
    )
    if not assignment.assigned_row_positions:
        return prepared_file

    schema = validate_dataframe_schema(
        assignment.dataframe,
        workbook_name=prepared_file.filename,
    )
    if schema.status is SchemaStatus.INVALID:
        status = FileProcessingStatus.INVALID_SCHEMA
    elif schema.status is SchemaStatus.REVIEW_REQUIRED:
        status = FileProcessingStatus.PENDING_MAPPING_APPROVAL
    else:
        status = FileProcessingStatus.READY
    return replace(
        prepared_file,
        source_dataframe=assignment.dataframe,
        schema_validation=schema,
        status=status,
        error=None,
        automatic_project_rows=assignment.assigned_row_positions,
    )


def _with_project_decision(
    prepared_file: PreparedFile,
    decision: dict[str, Any] | None,
) -> PreparedFile:
    if (
        decision is None
        or prepared_file.source_dataframe is None
        or prepared_file.schema_validation is None
        or decision.get("action") == "rejected"
    ):
        return prepared_file

    try:
        mapping_result = prepared_file.schema_validation.mapping_result
        current_project_result = validate_project_identity(
            prepared_file.source_dataframe,
            mapping_result,
        )
        if (
            decision.get("action") == "assignment"
            and current_project_result.status
            not in (
                ProjectIdentityStatus.MISSING_COLUMN,
                ProjectIdentityStatus.MISSING_VALUES,
            )
        ):
            return prepared_file
        if decision["action"] == "assignment":
            corrected_dataframe = apply_project_assignment(
                prepared_file.source_dataframe,
                mapping_result,
                decision["value"],
            )
        elif decision["action"] == "correction":
            corrected_dataframe = apply_project_value_corrections(
                prepared_file.source_dataframe,
                mapping_result,
                decision["corrections"],
            )
        else:
            raise ValueError("Unknown Project resolution decision.")
        schema = validate_dataframe_schema(
            corrected_dataframe,
            workbook_name=prepared_file.filename,
        )
    except (KeyError, TypeError, ValueError) as exc:
        return replace(
            prepared_file,
            status=FileProcessingStatus.FAILED,
            error=f"Could not apply the approved Project resolution: {exc}",
        )

    if schema.status is SchemaStatus.INVALID:
        status = FileProcessingStatus.INVALID_SCHEMA
    elif schema.status is SchemaStatus.REVIEW_REQUIRED:
        status = FileProcessingStatus.PENDING_MAPPING_APPROVAL
    else:
        status = FileProcessingStatus.READY
    return replace(
        prepared_file,
        source_dataframe=corrected_dataframe,
        schema_validation=schema,
        status=status,
        error=None,
    )


def _project_decision_key(
    upload_key: str,
    file_index: int,
    header_row: int | None,
) -> str:
    return f"project-decision-{upload_key}-{file_index}-{header_row}"


def _is_file_ready(prepared_file: PreparedFile) -> bool:
    project_result = _project_result(prepared_file)
    return (
        prepared_file.status is FileProcessingStatus.READY
        and prepared_file.schema_validation is not None
        and prepared_file.schema_validation.status is SchemaStatus.VALID
        and project_result is not None
        and project_result.status
        in (ProjectIdentityStatus.VALID, ProjectIdentityStatus.NO_RECORDS)
    )


def _overall_status(
    prepared_file: PreparedFile,
    project_result: ProjectIdentityResult | None,
) -> str:
    schema = prepared_file.schema_validation
    if prepared_file.status is FileProcessingStatus.PENDING_HEADER_REVIEW:
        return "REVIEW REQUIRED"
    if (
        prepared_file.status is FileProcessingStatus.FAILED
        or schema is None
        or schema.status is SchemaStatus.INVALID
    ):
        return "INVALID"
    if project_result is None or project_result.status in (
        ProjectIdentityStatus.INVALID_VALUES,
        ProjectIdentityStatus.INCONSISTENT_VALUES,
        ProjectIdentityStatus.CONFLICTING_COLUMNS,
    ):
        return "INVALID"
    if (
        schema.status is SchemaStatus.REVIEW_REQUIRED
        or project_result.status
        not in (ProjectIdentityStatus.VALID, ProjectIdentityStatus.NO_RECORDS)
    ):
        return "REVIEW REQUIRED"
    return "VALID"


def _render_project_resolution_controls(
    prepared_file: PreparedFile,
    decision_key: str,
    decisions: dict[str, dict[str, Any]],
) -> None:
    project_result = _project_result(prepared_file)
    dataframe = prepared_file.source_dataframe
    schema = prepared_file.schema_validation
    if project_result is None or dataframe is None or schema is None:
        return

    decision = decisions.get(decision_key)
    if decision and decision.get("action") == "rejected":
        st.warning(
            "The Project correction was rejected. Original Project values remain "
            "unchanged."
        )
        return
    if decision and decision.get("action") == "assignment":
        if (
            prepared_file.automatic_project_rows
            and project_result.status is ProjectIdentityStatus.VALID
        ):
            return
        st.success(
            f"Project assignment {decision['value']!r} approved and revalidated."
        )
        st.selectbox(
            "Project assignment",
            options=("", *APPROVED_PROJECT_VALUES),
            index=APPROVED_PROJECT_VALUES.index(decision["value"]) + 1,
            format_func=lambda value: value or "Select a project",
            key=f"{decision_key}-assignment",
            disabled=True,
        )
        return
    if decision and decision.get("action") == "correction":
        for original_value, suggested_value in decision["corrections"].items():
            st.success(
                f"Approved Project correction: {original_value!r} → "
                f"{suggested_value!r}; the in-memory copy was revalidated."
            )
        return

    if project_result.status in (
        ProjectIdentityStatus.MISSING_COLUMN,
        ProjectIdentityStatus.MISSING_VALUES,
    ):
        st.markdown(
            "**Project data is missing. Choose and approve an assignment for "
            "the missing values.**"
        )
        selected_project = st.selectbox(
            "Project assignment",
            options=("", *APPROVED_PROJECT_VALUES),
            format_func=lambda value: value or "Select a project",
            key=f"{decision_key}-assignment",
        )
        if st.button(
            f"Approve Project assignment for {prepared_file.filename}",
            key=f"{decision_key}-approve-assignment",
            disabled=not selected_project,
        ):
            decisions[decision_key] = {
                "action": "assignment",
                "value": selected_project,
            }
            st.rerun()
        return

    suggestions = suggest_project_value_corrections(
        dataframe,
        schema.mapping_result,
    )
    if suggestions:
        st.markdown("**Project value correction requires explicit approval.**")
        for suggestion_index, suggestion in enumerate(suggestions):
            st.write(
                {
                    "Original value": suggestion.original_value,
                    "Suggested value": suggestion.suggested_value,
                    "Data rows": suggestion.row_positions,
                }
            )
            approve_col, reject_col = st.columns(2)
            if approve_col.button(
                f"Approve suggested correction for {prepared_file.filename}",
                key=f"{decision_key}-approve-correction-{suggestion_index}",
            ):
                decisions[decision_key] = {
                    "action": "correction",
                    "corrections": {
                        suggestion.original_value: suggestion.suggested_value
                    },
                }
                st.rerun()
            if reject_col.button(
                f"Reject suggested correction for {prepared_file.filename}",
                key=f"{decision_key}-reject-correction-{suggestion_index}",
            ):
                decisions[decision_key] = {"action": "rejected"}
                st.rerun()


def _render_prepared_file(
    prepared_file: PreparedFile,
    decision_key: str,
    decisions: dict[str, dict[str, Any]],
    header_key: str,
    manual_header_rows: dict[str, int],
    header_review_candidates: dict[str, tuple[int, ...]],
) -> None:
    project_result = _project_result(prepared_file)
    overall_status = _overall_status(prepared_file, project_result)
    with st.expander(
        f"{overall_status} | {prepared_file.filename}",
        expanded=overall_status != "VALID",
    ):
        dataframe = prepared_file.source_dataframe
        row_count = len(dataframe) if dataframe is not None else "Unavailable"
        st.write(f"**Rows detected:** {row_count}")
        if prepared_file.header_row is not None:
            st.write(f"**Excel header row:** {prepared_file.header_row}")
        elif prepared_file.header_candidates:
            st.write(
                "**Excel header row:** Manual review required "
                f"({', '.join(map(str, prepared_file.header_candidates))})"
            )
        elif prepared_file.error == "Header not detected within the first 5 rows.":
            st.write("**Excel header row:** Not detected")
        else:
            st.write("**Excel header row:** Unavailable")

        schema = prepared_file.schema_validation
        if schema is None:
            st.write("**Schema status:** Unavailable")
            st.write("**Missing columns:** Unavailable")
        else:
            st.write(f"**Schema status:** {schema.status.value}")
            missing_columns = schema.missing_columns
            st.write(
                "**Missing columns:** "
                + (", ".join(missing_columns) if missing_columns else "None")
            )
            if schema.unexpected_columns:
                st.write(
                    "**Extra/unmapped columns:** "
                    + ", ".join(schema.unexpected_columns)
                )
            if schema.duplicate_source_columns:
                st.error(
                    "Duplicate source headers: "
                    + ", ".join(schema.duplicate_source_columns)
                )
            if schema.conflicting_targets:
                st.error(
                    "Conflicting mapping targets: "
                    + ", ".join(schema.conflicting_targets)
                )
            if schema.mapping_result.suggestions:
                st.markdown("**Column-name suggestions (not applied):**")
                for suggestion in schema.mapping_result.suggestions:
                    standard_name = suggestion.target_column or "Ambiguous"
                    st.write(
                        f"- Source `{suggestion.original_column}` → "
                        f"`{standard_name}`; candidates: "
                        f"{', '.join(suggestion.candidate_targets) or 'None'}"
                    )

        if project_result is None:
            st.write("**Project identity status:** Unavailable")
        else:
            project_label = project_result.status.value
            if project_result.project:
                project_label += f" ({project_result.project})"
            st.write(f"**Project identity status:** {project_label}")
            if prepared_file.automatic_project_rows:
                st.success(
                    "Project automatically assigned as '4G Saturation' from "
                    "Circle for data rows "
                    f"{list(prepared_file.automatic_project_rows)}."
                )
            for finding in project_result.findings:
                st.warning(finding)
            if project_result.status in (
                ProjectIdentityStatus.MISSING_COLUMN,
                ProjectIdentityStatus.MISSING_VALUES,
            ):
                st.warning(
                    "Explicit Project resolution is required for values not "
                    "identified from Circle."
                )
            elif project_result.status in (
                ProjectIdentityStatus.INVALID_VALUES,
                ProjectIdentityStatus.INCONSISTENT_VALUES,
            ):
                st.error(
                    "Resolve unsupported or inconsistent Project values before "
                    "consolidation. Only recognized suggestions can be approved."
                )
            decision = decisions.get(decision_key)
            if project_result.status in (
                ProjectIdentityStatus.MISSING_COLUMN,
                ProjectIdentityStatus.MISSING_VALUES,
                ProjectIdentityStatus.INVALID_VALUES,
                ProjectIdentityStatus.INCONSISTENT_VALUES,
                ProjectIdentityStatus.MAPPING_REVIEW_REQUIRED,
                ProjectIdentityStatus.CONFLICTING_COLUMNS,
            ) or (
                decision is not None
                and decision.get("action") in ("assignment", "correction")
            ):
                _render_project_resolution_controls(
                    prepared_file,
                    decision_key,
                    decisions,
                )
        if prepared_file.error:
            if prepared_file.status is FileProcessingStatus.PENDING_HEADER_REVIEW:
                st.warning(prepared_file.error)
            else:
                st.error(prepared_file.error)
        candidate_rows = (
            prepared_file.header_candidates
            or header_review_candidates.get(header_key, ())
        )
        if candidate_rows:
            selected_header_row = st.selectbox(
                f"Header row to use for {prepared_file.filename}",
                options=candidate_rows,
                key=f"header-candidate-{header_key}",
            )
            if st.button(
                f"Use selected header row for {prepared_file.filename}",
                key=f"use-header-{header_key}",
            ):
                manual_header_rows[header_key] = int(selected_header_row)
                st.rerun()


def _bucket_validation_for_file(
    prepared_file: PreparedFile,
) -> tuple[BucketValidationResult | None, str | None]:
    if (
        prepared_file.source_dataframe is None
        or prepared_file.schema_validation is None
    ):
        return None, "Workbook data or schema mapping is unavailable."
    try:
        mapped_dataframe = apply_approved_mappings(
            prepared_file.source_dataframe,
            prepared_file.schema_validation.mapping_result,
        )
        result = validate_bucket_combinations(
            mapped_dataframe,
            source_filename=prepared_file.filename,
            header_row=prepared_file.header_row or 1,
        )
    except ValueError as exc:
        return None, str(exc)
    return result, None


def _render_bucket_validation(
    prepared_files: tuple[PreparedFile, ...],
) -> None:
    bucket_results = [
        _bucket_validation_for_file(prepared_file)
        for prepared_file in prepared_files
    ]
    st.subheader("Bucket Validation")
    file_rows = []
    available_results: list[BucketValidationResult] = []
    issues_by_record: dict[tuple[str, int], dict[str, Any]] = {}
    for prepared_file, (result, error) in zip(
        prepared_files,
        bucket_results,
        strict=True,
    ):
        if result is None:
            file_rows.append(
                {
                    "Filename": prepared_file.filename,
                    "Valid records": "Unavailable",
                    "Invalid records": "Unavailable",
                    "Details": error or "Bucket validation unavailable.",
                }
            )
            continue
        available_results.append(result)
        file_rows.append(
            {
                "Filename": prepared_file.filename,
                "Valid records": result.valid_records,
                "Invalid records": result.invalid_records,
                "Details": "",
            }
        )
        for issue in result.issues:
            key = (issue.source_filename, issue.excel_row_number)
            record = issues_by_record.setdefault(
                key,
                {
                    "Source filename": issue.source_filename,
                    "Excel row number": issue.excel_row_number,
                    "Final Bucket": issue.final_bucket,
                    "Bucket - 2": issue.bucket_2,
                    "Error reason": [],
                },
            )
            record["Error reason"].append(issue.reason)

    st.write(
        {
            "Complete batch — valid records": sum(
                result.valid_records for result in available_results
            ),
            "Complete batch — invalid records": sum(
                result.invalid_records for result in available_results
            ),
        }
    )
    st.dataframe(file_rows, hide_index=True, width="stretch")
    if issues_by_record:
        issue_rows = [
            {
                **record,
                "Error reason": "; ".join(record["Error reason"]),
            }
            for record in issues_by_record.values()
        ]
        st.dataframe(issue_rows, hide_index=True, width="stretch")
    elif available_results:
        st.success("All bucket combinations are valid.")
    else:
        st.info("Bucket validation could not run for the uploaded workbooks.")
    st.caption(
        "Bucket values are compared case-insensitively after trimming outer "
        "spaces. Original values are preserved; mismatches are not corrected."
    )


def _render_validation_report(
    batch: PreparedBatchResult,
    decision_keys: list[str],
    decisions: dict[str, dict[str, Any]],
    header_keys: list[str],
    manual_header_rows: dict[str, int],
    header_review_candidates: dict[str, tuple[int, ...]],
) -> None:
    st.subheader("Per-file validation report")
    summary_rows = []
    for prepared_file in batch.files:
        project_result = _project_result(prepared_file)
        row_count = (
            len(prepared_file.source_dataframe)
            if prepared_file.source_dataframe is not None
            else None
        )
        summary_rows.append(
            {
                "Filename": prepared_file.filename,
                "Rows": row_count if row_count is not None else "Unavailable",
                "Excel header row": (
                    prepared_file.header_row
                    if prepared_file.header_row is not None
                    else "Manual review" if prepared_file.header_candidates
                    else "Not detected" if prepared_file.error
                    == "Header not detected within the first 5 rows."
                    else "Unavailable"
                ),
                "Status": _overall_status(prepared_file, project_result),
            }
        )
    st.dataframe(summary_rows, hide_index=True, width="stretch")
    _render_bucket_validation(batch.files)
    for prepared_file, decision_key, header_key in zip(
        batch.files,
        decision_keys,
        header_keys,
        strict=True,
    ):
        _render_prepared_file(
            prepared_file,
            decision_key,
            decisions,
            header_key,
            manual_header_rows,
            header_review_candidates,
        )

    st.caption(
        "Validation reads only the RCA_Data worksheet. Suggested column mappings "
        "are not approved. Project corrections are applied only to in-memory copies "
        "after explicit approval."
    )


def _render_consolidation_result(result: ConsolidationResult) -> None:
    st.subheader("Consolidated RCA_Data")
    st.write(f"**Batch status:** {result.status.value}")
    st.write(f"**Duplicate records removed:** {result.duplicates_removed}")
    st.write(f"**Final records:** {len(result.dataframe)}")
    st.subheader("Record filtering audit")
    audit = result.filter_audit
    st.write(f"**Reporting date:** {audit.reporting_date.isoformat()}")
    st.write(
        {
            "Original records read": audit.original_records,
            "Records matching reporting date": (
                audit.records_matching_reporting_date
            ),
            "Records remaining after O&M filter": audit.records_after_om_filter,
            "Records remaining after outage filter": (
                audit.records_after_outage_filter
            ),
            "Excluded by reporting-date filter": (
                audit.excluded_by_reporting_date
            ),
            "Excluded by O&M filter": audit.excluded_by_om_filter,
            "Excluded by outage-minutes filter": (
                audit.excluded_by_outage_filter
            ),
            "Records after duplicate removal": (
                audit.records_after_duplicate_removal
            ),
            "Blank Date values": audit.blank_date_values,
            "Invalid Date values": audit.invalid_date_values,
            "Blank O&M Start values": audit.blank_om_values,
            "Invalid O&M Start values": audit.invalid_om_values,
            "Blank Outage Min. values": audit.blank_outage_values,
            "Invalid Outage Min. values": audit.invalid_outage_values,
        }
    )
    per_file_audits = []
    for file_result in result.file_results:
        file_audit = file_result.filter_audit
        if file_audit is None:
            per_file_audits.append(
                {
                    "Filename": file_result.filename,
                    "Filter audit": "Unavailable",
                }
            )
            continue
        per_file_audits.append(
            {
                "Filename": file_result.filename,
                "Original records read": file_audit.original_records,
                "Matching reporting date": (
                    file_audit.records_matching_reporting_date
                ),
                "After O&M filter": file_audit.records_after_om_filter,
                "After outage filter": file_audit.records_after_outage_filter,
                "Excluded by date": file_audit.excluded_by_reporting_date,
                "Excluded by O&M": file_audit.excluded_by_om_filter,
                "Excluded by outage": file_audit.excluded_by_outage_filter,
                "After duplicate removal": (
                    file_audit.records_after_duplicate_removal
                ),
                "Duplicates removed": file_audit.duplicates_removed,
                "Blank Date": file_audit.blank_date_values,
                "Invalid Date": file_audit.invalid_date_values,
                "Blank O&M Start": file_audit.blank_om_values,
                "Invalid O&M Start": file_audit.invalid_om_values,
                "Blank Outage Min.": file_audit.blank_outage_values,
                "Invalid Outage Min.": file_audit.invalid_outage_values,
            }
        )
    st.dataframe(per_file_audits, hide_index=True, width="stretch")
    st.caption(
        "Date findings cover all input rows; O&M findings cover rows matching "
        "the selected date; outage findings cover rows retained by the O&M filter."
    )
    if result.dataframe.empty:
        st.info(
            "No records matched the selected reporting date and all required "
            "record filters."
        )
    else:
        st.dataframe(result.dataframe, hide_index=True, width="stretch")
    st.download_button(
        "Download consolidated Excel workbook",
        data=write_rca_workbook(result.dataframe),
        file_name="RCA_Consolidated.xlsx",
        mime=(
            "application/vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet"
        ),
        width="stretch",
    )
    for file_result in result.file_results:
        if file_result.error:
            st.error(f"{file_result.filename}: {file_result.error}")

st.set_page_config(
    page_title="RCA Data Consolidation System",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    .stApp {
        background: #f4f7fb;
    }
    .block-container {
        max-width: 1180px;
        padding-top: 2rem;
        padding-bottom: 3rem;
    }
    section[data-testid="stSidebar"] {
        background: #10233f;
    }
    section[data-testid="stSidebar"] * {
        color: #eef4ff;
    }
    .brand-mark {
        color: #91c8ff;
        font-size: 0.75rem;
        font-weight: 700;
        letter-spacing: 0.12em;
        text-transform: uppercase;
    }
    .sidebar-app-name {
        font-size: 1.15rem;
        font-weight: 700;
        line-height: 1.35;
        margin: 0.35rem 0 1.75rem;
    }
    .nav-heading {
        color: #91a6c3 !important;
        font-size: 0.72rem;
        font-weight: 700;
        letter-spacing: 0.1em;
        margin-bottom: 0.6rem;
        text-transform: uppercase;
    }
    .nav-item {
        border-radius: 0.5rem;
        color: #d6e1f0 !important;
        display: block;
        margin: 0.25rem 0;
        padding: 0.65rem 0.8rem;
    }
    .nav-item.active {
        background: #1c3d66;
        color: #ffffff !important;
        font-weight: 700;
    }
    .hero {
        background: linear-gradient(115deg, #12345a, #1d5680);
        border-radius: 1rem;
        color: #ffffff;
        margin-bottom: 1.5rem;
        padding: 2rem 2.2rem;
    }
    .hero-label {
        color: #b7d9f7;
        font-size: 0.75rem;
        font-weight: 700;
        letter-spacing: 0.12em;
        text-transform: uppercase;
    }
    .hero h1 {
        color: #ffffff;
        font-size: 2.15rem;
        margin: 0.55rem 0;
    }
    .hero p {
        color: #e4effa;
        font-size: 1rem;
        margin: 0;
        max-width: 760px;
    }
    .project-card {
        background: #ffffff;
        border: 1px solid #e1e8f0;
        border-radius: 0.8rem;
        min-height: 108px;
        padding: 1.15rem 1.3rem;
    }
    .project-card h3 {
        color: #17385c;
        font-size: 1.05rem;
        margin: 0 0 0.4rem;
    }
    .project-card p {
        color: #61738a;
        font-size: 0.9rem;
        margin: 0;
    }
    .section-note {
        color: #61738a;
        font-size: 0.9rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

with st.sidebar:
    st.markdown('<div class="brand-mark">RCA WORKSPACE</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="sidebar-app-name">RCA Data<br>Consolidation System</div>',
        unsafe_allow_html=True,
    )
    st.markdown('<div class="nav-heading">Navigation</div>', unsafe_allow_html=True)
    st.markdown('<div class="nav-item active">Home</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="nav-item">Upload &amp; Consolidation</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="nav-item">Validation Report</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="nav-item">Consolidated Results</div>',
        unsafe_allow_html=True,
    )
    st.divider()
    st.caption("Workbook validation and consolidation")

st.markdown(
    """
    <div class="hero">
        <div class="hero-label">RCA Data Operations</div>
        <h1>RCA Data Consolidation System</h1>
        <p>
            Bring RCA workbooks together in a consistent master dataset while
            retaining project identity and surfacing data issues for review.
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)

st.subheader("Supported projects")
st.markdown(
    '<p class="section-note">Valid existing Project values are preserved. Missing '
    "assignments and recognized corrections require per-file approval and are applied "
    "only to in-memory copies.</p>",
    unsafe_allow_html=True,
)
project_columns = st.columns(2)
with project_columns[0]:
    st.markdown(
        """
        <div class="project-card">
            <h3>LWE</h3>
            <p>Supported project identifier for RCA records.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
with project_columns[1]:
    st.markdown(
        """
        <div class="project-card">
            <h3>4G Saturation</h3>
            <p>Supported project identifier for RCA records.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

st.subheader("Upload workbooks")
st.markdown(
    '<p class="section-note">Select one or more Excel workbooks to validate the '
    "RCA_Data worksheet. Configure each workbook's header row independently; "
    "changing a row re-runs its validation.</p>",
    unsafe_allow_html=True,
)
uploaded_files = st.file_uploader(
    "Excel workbooks",
    type=["xlsx", "xlsm"],
    accept_multiple_files=True,
    help="Supported formats: .xlsx and .xlsm.",
)

if uploaded_files:
    st.markdown("#### Selected files")
    file_details = [
        {
            "Filename": uploaded_file.name,
            "Size": (
                f"{uploaded_file.size / (1024 * 1024):.2f} MB"
                if uploaded_file.size >= 1024 * 1024
                else f"{uploaded_file.size / 1024:.1f} KB"
            ),
        }
        for uploaded_file in uploaded_files
    ]
    st.dataframe(
        file_details,
        hide_index=True,
        width="stretch",
    )
    upload_signature = _upload_signature(uploaded_files)
    upload_key = hashlib.sha256(repr(upload_signature).encode()).hexdigest()[:16]
    st.caption(
        "Header rows are detected automatically within the first five rows. "
        "Only ambiguous detections require manual review."
    )
    manual_header_rows = st.session_state.setdefault("manual_header_rows", {})
    header_review_candidates = st.session_state.setdefault(
        "header_review_candidates",
        {},
    )
    header_keys = [
        f"{upload_key}-{file_index}"
        for file_index in range(len(uploaded_files))
    ]
    manual_header_signature = tuple(
        (key, manual_header_rows.get(key)) for key in header_keys
    )
    configuration_signature = (upload_signature, manual_header_signature)
    validate_clicked = st.button(
        "Validate Workbooks",
        type="primary",
        width="stretch",
    )
    if (
        st.session_state.get("prepared_signature") != configuration_signature
        or validate_clicked
    ):
        with st.spinner("Reading and validating each workbook..."):
            st.session_state["prepared_batch"] = _prepare_uploaded_files(
                uploaded_files,
                manual_header_rows,
                upload_key,
            )
            st.session_state["prepared_signature"] = configuration_signature
            st.session_state.pop("consolidation_run", None)
            for file_index, prepared_file in enumerate(
                st.session_state["prepared_batch"].files
            ):
                if prepared_file.header_candidates:
                    header_review_candidates[header_keys[file_index]] = (
                        prepared_file.header_candidates
                    )

    prepared_batch = st.session_state.get("prepared_batch")
    if (
        prepared_batch is not None
        and st.session_state.get("prepared_signature") == configuration_signature
    ):
        decisions = st.session_state.setdefault("project_decisions", {})
        decision_keys = [
            _project_decision_key(
                upload_key,
                file_index,
                prepared_file.header_row,
            )
            for file_index, prepared_file in enumerate(prepared_batch.files)
        ]
        corrected_files = tuple(
            _with_project_decision(
                _with_circle_project_assignment(prepared_file),
                decisions.get(decision_key),
            )
            for prepared_file, decision_key in zip(
                prepared_batch.files,
                decision_keys,
                strict=True,
            )
        )
        corrected_batch = PreparedBatchResult(files=corrected_files)
        _render_validation_report(
            corrected_batch,
            decision_keys,
            decisions,
            header_keys,
            manual_header_rows,
            header_review_candidates,
        )
        can_consolidate = bool(corrected_files) and all(
            _is_file_ready(prepared_file) for prepared_file in corrected_files
        )
        if not can_consolidate:
            st.info(
                "Consolidation stays disabled until every workbook has a valid "
                "schema and Project identity, with required corrections approved."
            )
        selected_reporting_date = None
        if can_consolidate:
            st.subheader("Reporting date")
            selected_reporting_date = st.date_input(
                "Select the reporting date to include",
                value=None,
                key=f"reporting-date-{upload_key}",
                help="Choose the calendar date to retain in every workbook.",
            )
            if selected_reporting_date is None:
                st.info("Select a reporting date before starting consolidation.")
        can_start_consolidation = (
            can_consolidate and selected_reporting_date is not None
        )
        decision_signature = tuple(
            (key, repr(decisions.get(key))) for key in decision_keys
        )
        workflow_signature = (
            configuration_signature,
            decision_signature,
            selected_reporting_date,
        )
    else:
        corrected_batch = None
        can_consolidate = False
        can_start_consolidation = False
        selected_reporting_date = None
        workflow_signature = None
else:
    st.info("No files have been uploaded. Choose one or more .xlsx or .xlsm files to begin.")
    corrected_batch = None
    can_consolidate = False
    can_start_consolidation = False
    selected_reporting_date = None
    workflow_signature = None

if st.button(
    "Start Consolidation",
    disabled=not can_start_consolidation,
    width="stretch",
    help=(
        "Resolve schema and Project findings and select a reporting date."
        if not can_start_consolidation
        else "Consolidate validated workbook data."
    ),
):
    if corrected_batch is not None and selected_reporting_date is not None:
        with st.spinner("Consolidating validated workbooks..."):
            result = consolidate_prepared_files(
                corrected_batch,
                reporting_date=selected_reporting_date,
            )
        st.session_state["consolidation_run"] = {
            "signature": workflow_signature,
            "result": result,
        }

if workflow_signature is not None:
    consolidation_run = st.session_state.get("consolidation_run")
    if (
        consolidation_run is not None
        and consolidation_run["signature"] == workflow_signature
    ):
        _render_consolidation_result(consolidation_run["result"])