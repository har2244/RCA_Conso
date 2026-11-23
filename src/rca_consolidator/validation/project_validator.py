"""Validate Project identity without changing source values."""

from dataclasses import dataclass
from enum import Enum
import re
import unicodedata
from typing import Mapping

import pandas as pd

from rca_consolidator.processing.column_mapper import (
    ColumnMapping,
    ColumnMappingResult,
    MappingStatus,
)
from rca_consolidator.processing.data_cleaner import is_blank_value


APPROVED_PROJECT_VALUES = ("LWE", "4G Saturation")
PROJECT_VALUE_SUGGESTIONS = {"4G-Saturation": "4G Saturation"}


class ProjectIdentityStatus(str, Enum):
    """Project identity outcome for one source workbook."""

    VALID = "VALID"
    NO_RECORDS = "NO_RECORDS"
    MISSING_COLUMN = "MISSING_COLUMN"
    MAPPING_REVIEW_REQUIRED = "MAPPING_REVIEW_REQUIRED"
    CONFLICTING_COLUMNS = "CONFLICTING_COLUMNS"
    MISSING_VALUES = "MISSING_VALUES"
    INVALID_VALUES = "INVALID_VALUES"
    INCONSISTENT_VALUES = "INCONSISTENT_VALUES"


@dataclass(frozen=True)
class ProjectIdentityResult:
    """Project identity status and row-level findings."""

    status: ProjectIdentityStatus
    project: str | None = None
    findings: tuple[str, ...] = ()


@dataclass(frozen=True)
class ProjectValueCorrection:
    """A known Project value suggestion and its source data-row positions."""

    original_value: str
    suggested_value: str
    row_positions: tuple[int, ...]


@dataclass(frozen=True)
class CircleProjectAssignmentResult:
    """In-memory Project assignments inferred from matching Circle values."""

    dataframe: pd.DataFrame
    assigned_row_positions: tuple[int, ...]


_FOUR_G_SATURATION_PATTERN = re.compile(
    r"(?<!\w)4\s*g\s*satu(?:ration)?(?!\w)"
)


def _circle_source_index(mapping_result: ColumnMappingResult) -> int | None:
    if "Circle" in mapping_result.conflicting_targets:
        return None
    circle_mappings = [
        mapping
        for mapping in mapping_result.mappings
        if mapping.target_column == "Circle"
        and mapping.status
        in (
            MappingStatus.EXACT_MATCH,
            MappingStatus.NORMALIZED_MATCH,
            MappingStatus.APPROVED,
        )
        and mapping.source_index is not None
    ]
    if len(circle_mappings) != 1:
        return None
    return circle_mappings[0].source_index


def _is_4g_saturation_circle(value: object) -> bool:
    if not isinstance(value, str):
        return False
    normalized = unicodedata.normalize("NFKC", value).casefold()
    normalized = re.sub(r"[\W_]+", " ", normalized)
    return _FOUR_G_SATURATION_PATTERN.search(normalized) is not None


def apply_circle_project_assignment(
    dataframe: pd.DataFrame,
    mapping_result: ColumnMappingResult,
) -> CircleProjectAssignmentResult:
    """Fill missing Project values for rows whose mapped Circle identifies 4G.

    Existing nonblank Project values are preserved. Only exact, normalized, or
    explicitly approved Circle mappings can supply an automatic assignment.
    """
    corrected = dataframe.copy(deep=True)
    corrected.attrs = dataframe.attrs.copy()
    circle_source_index = _circle_source_index(mapping_result)
    if circle_source_index is None:
        return CircleProjectAssignmentResult(corrected, ())

    project_source_index = _project_source_index(mapping_result)
    if project_source_index is None:
        project_suggestions = [
            mapping
            for mapping in mapping_result.suggestions
            if "Project" in mapping.candidate_targets
        ]
        if (
            "Project" not in mapping_result.missing_columns
            or project_suggestions
        ):
            return CircleProjectAssignmentResult(corrected, ())
    else:
        existing_values = corrected.iloc[:, project_source_index].tolist()
        if any(
            not is_blank_value(value) and value != "4G Saturation"
            for value in existing_values
        ):
            return CircleProjectAssignmentResult(corrected, ())

    circle_values = corrected.iloc[:, circle_source_index].tolist()
    matching_positions = tuple(
        row_position
        for row_position, value in enumerate(circle_values, start=1)
        if _is_4g_saturation_circle(value)
    )
    if not matching_positions:
        return CircleProjectAssignmentResult(corrected, ())

    if project_source_index is None:
        corrected["Project"] = pd.NA
        project_source_index = corrected.columns.get_loc("Project")

    project_values = corrected.iloc[:, project_source_index].tolist()
    assigned_positions = tuple(
        row_position
        for row_position in matching_positions
        if is_blank_value(project_values[row_position - 1])
    )
    if assigned_positions:
        project_values = corrected.iloc[:, project_source_index].tolist()
        for row_position in assigned_positions:
            project_values[row_position - 1] = "4G Saturation"
        corrected.iloc[:, project_source_index] = project_values
    return CircleProjectAssignmentResult(corrected, assigned_positions)


def _project_source_mappings(
    mapping_result: ColumnMappingResult,
) -> list[ColumnMapping]:
    return [
        mapping
        for mapping in mapping_result.mappings
        if mapping.target_column == "Project"
        and mapping.status
        in (
            MappingStatus.EXACT_MATCH,
            MappingStatus.NORMALIZED_MATCH,
            MappingStatus.APPROVED,
        )
        and mapping.source_index is not None
    ]


def _project_source_index(mapping_result: ColumnMappingResult) -> int | None:
    if "Project" in mapping_result.conflicting_targets:
        return None
    project_mappings = _project_source_mappings(mapping_result)
    if len(project_mappings) != 1:
        return None
    return project_mappings[0].source_index


def validate_project_identity(
    dataframe: pd.DataFrame,
    mapping_result: ColumnMappingResult,
) -> ProjectIdentityResult:
    """Validate the mapped Project source column without modifying the frame."""
    if "Project" in mapping_result.conflicting_targets:
        return ProjectIdentityResult(
            status=ProjectIdentityStatus.CONFLICTING_COLUMNS,
            findings=("Multiple source columns conflict for Project.",),
        )

    project_mappings = _project_source_mappings(mapping_result)
    if len(project_mappings) > 1:
        return ProjectIdentityResult(
            status=ProjectIdentityStatus.CONFLICTING_COLUMNS,
            findings=("Multiple source columns map to Project.",),
        )
    if not project_mappings:
        project_suggestions = [
            mapping
            for mapping in mapping_result.suggestions
            if "Project" in mapping.candidate_targets
        ]
        if project_suggestions:
            return ProjectIdentityResult(
                status=ProjectIdentityStatus.MAPPING_REVIEW_REQUIRED,
                findings=(
                    "A source column may map to Project and requires approval.",
                ),
            )
        if "Project" in mapping_result.missing_columns:
            return ProjectIdentityResult(
                status=ProjectIdentityStatus.MISSING_COLUMN,
                findings=(
                    "Project column is missing; explicit assignment is required.",
                ),
            )
        return ProjectIdentityResult(
            status=ProjectIdentityStatus.MAPPING_REVIEW_REQUIRED,
            findings=("Project mapping requires review.",),
        )

    source_position = project_mappings[0].source_index
    project_values = dataframe.iloc[:, source_position].tolist()
    if not project_values:
        return ProjectIdentityResult(status=ProjectIdentityStatus.NO_RECORDS)

    blank_rows = [
        row_position + 1
        for row_position, value in enumerate(project_values)
        if is_blank_value(value)
    ]
    invalid_values = [
        (row_position + 1, value)
        for row_position, value in enumerate(project_values)
        if not is_blank_value(value)
        and not (
            isinstance(value, str)
            and value in APPROVED_PROJECT_VALUES
        )
    ]
    distinct_projects = {
        value
        for value in project_values
        if isinstance(value, str) and value in APPROVED_PROJECT_VALUES
    }

    findings: list[str] = []
    if blank_rows:
        findings.append(f"Blank Project values at data rows {blank_rows}.")
    if invalid_values:
        findings.append(
            "Unsupported Project values: "
            + ", ".join(f"row {row}: {value!r}" for row, value in invalid_values)
            + f"; approved values are {APPROVED_PROJECT_VALUES}."
        )
    if len(distinct_projects) > 1:
        findings.append(
            "Inconsistent Project values in one workbook: "
            + ", ".join(sorted(distinct_projects))
            + "."
        )

    if invalid_values or len(distinct_projects) > 1:
        status = ProjectIdentityStatus.INCONSISTENT_VALUES if (
            len(distinct_projects) > 1 and not invalid_values
        ) else ProjectIdentityStatus.INVALID_VALUES
        return ProjectIdentityResult(
            status=status,
            findings=tuple(findings),
        )
    if blank_rows:
        return ProjectIdentityResult(
            status=ProjectIdentityStatus.MISSING_VALUES,
            findings=tuple(findings),
        )

    return ProjectIdentityResult(
        status=ProjectIdentityStatus.VALID,
        project=next(iter(distinct_projects)),
    )


def suggest_project_value_corrections(
    dataframe: pd.DataFrame,
    mapping_result: ColumnMappingResult,
) -> tuple[ProjectValueCorrection, ...]:
    """Suggest only explicitly recognized variants of approved Project values."""
    source_index = _project_source_index(mapping_result)
    if source_index is None:
        return ()

    values = dataframe.iloc[:, source_index].tolist()
    return tuple(
        ProjectValueCorrection(
            original_value=original_value,
            suggested_value=suggested_value,
            row_positions=tuple(
                row_position
                for row_position, value in enumerate(values, start=1)
                if isinstance(value, str) and value == original_value
            ),
        )
        for original_value, suggested_value in PROJECT_VALUE_SUGGESTIONS.items()
        if any(
            isinstance(value, str) and value == original_value
            for value in values
        )
    )


def apply_project_assignment(
    dataframe: pd.DataFrame,
    mapping_result: ColumnMappingResult,
    project_value: str,
) -> pd.DataFrame:
    """Return a copy with an explicitly approved value for missing Project data."""
    if project_value not in APPROVED_PROJECT_VALUES:
        raise ValueError(
            f"Project assignment must be one of {APPROVED_PROJECT_VALUES}."
        )
    identity_result = validate_project_identity(dataframe, mapping_result)
    corrected = dataframe.copy(deep=True)
    corrected.attrs = dataframe.attrs.copy()
    if identity_result.status is ProjectIdentityStatus.MISSING_COLUMN:
        corrected["Project"] = project_value
        return corrected
    if identity_result.status is not ProjectIdentityStatus.MISSING_VALUES:
        raise ValueError(
            "Project assignment is allowed only when Project is missing "
            "or has blank values."
        )

    source_index = _project_source_index(mapping_result)
    if source_index is None:
        raise ValueError("Project source column is not uniquely mapped.")
    values = corrected.iloc[:, source_index].tolist()
    blank_positions = [
        row_position
        for row_position, value in enumerate(values)
        if is_blank_value(value)
    ]
    if not blank_positions:
        raise ValueError("No blank Project values are available for assignment.")
    for row_position in blank_positions:
        values[row_position] = project_value
    corrected.iloc[:, source_index] = values
    return corrected


def apply_project_value_corrections(
    dataframe: pd.DataFrame,
    mapping_result: ColumnMappingResult,
    approved_corrections: Mapping[str, str],
) -> pd.DataFrame:
    """Return a copy with only approved, recognized Project variants corrected."""
    suggestions = {
        suggestion.original_value: suggestion.suggested_value
        for suggestion in suggest_project_value_corrections(
            dataframe,
            mapping_result,
        )
    }
    if not approved_corrections:
        corrected = dataframe.copy(deep=True)
        corrected.attrs = dataframe.attrs.copy()
        return corrected
    if any(
        suggestions.get(original_value) != suggested_value
        for original_value, suggested_value in approved_corrections.items()
    ):
        raise ValueError("Project correction is not a currently suggested value.")

    source_index = _project_source_index(mapping_result)
    if source_index is None:
        raise ValueError("Project source column is not uniquely mapped.")

    corrected = dataframe.copy(deep=True)
    corrected.attrs = dataframe.attrs.copy()
    values = corrected.iloc[:, source_index].tolist()
    for original_value, suggested_value in approved_corrections.items():
        corrected.iloc[:, source_index] = [
            suggested_value
            if isinstance(value, str) and value == original_value
            else value
            for value in values
        ]
        values = corrected.iloc[:, source_index].tolist()
    return corrected
