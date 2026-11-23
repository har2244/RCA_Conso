"""Tests for workbook-level Project identity validation."""

import pandas as pd
import pytest

from rca_consolidator.processing.column_mapper import map_columns
from rca_consolidator.validation.project_validator import (
    ProjectIdentityStatus,
    apply_circle_project_assignment,
    apply_project_assignment,
    apply_project_value_corrections,
    suggest_project_value_corrections,
    validate_project_identity,
)


@pytest.mark.parametrize("project", ["LWE", "4G Saturation"])
def test_accepts_each_approved_project(project: str) -> None:
    dataframe = pd.DataFrame({"Project": [project]})

    result = validate_project_identity(
        dataframe,
        map_columns(list(dataframe.columns)),
    )

    assert result.status is ProjectIdentityStatus.VALID
    assert result.project == project
    pd.testing.assert_frame_equal(dataframe, pd.DataFrame({"Project": [project]}))


def test_reports_missing_project_column() -> None:
    dataframe = pd.DataFrame({"Circle": ["North"]})

    result = validate_project_identity(
        dataframe,
        map_columns(list(dataframe.columns)),
    )

    assert result.status is ProjectIdentityStatus.MISSING_COLUMN


def test_requires_mapping_review_for_fuzzy_project_header() -> None:
    dataframe = pd.DataFrame({"Projec": ["LWE"]})

    result = validate_project_identity(
        dataframe,
        map_columns(list(dataframe.columns)),
    )

    assert result.status is ProjectIdentityStatus.MAPPING_REVIEW_REQUIRED


def test_reports_blank_project_values_without_filling_them() -> None:
    dataframe = pd.DataFrame({"Project": ["LWE", " "]})
    original = dataframe.copy(deep=True)

    result = validate_project_identity(
        dataframe,
        map_columns(list(dataframe.columns)),
    )

    assert result.status is ProjectIdentityStatus.MISSING_VALUES
    assert "data rows [2]" in result.findings[0]
    pd.testing.assert_frame_equal(dataframe, original)


def test_rejects_unapproved_project_value() -> None:
    dataframe = pd.DataFrame({"Project": ["4G-Saturation"]})

    result = validate_project_identity(
        dataframe,
        map_columns(list(dataframe.columns)),
    )

    assert result.status is ProjectIdentityStatus.INVALID_VALUES
    assert "4G-Saturation" in result.findings[0]


def test_rejects_mixed_project_values_within_one_workbook() -> None:
    dataframe = pd.DataFrame({"Project": ["LWE", "4G Saturation"]})

    result = validate_project_identity(
        dataframe,
        map_columns(list(dataframe.columns)),
    )

    assert result.status is ProjectIdentityStatus.INCONSISTENT_VALUES
    assert "4G Saturation, LWE" in result.findings[0]


def test_project_assignment_returns_copy_only_for_missing_column() -> None:
    dataframe = pd.DataFrame({"Circle": ["North"]})
    original = dataframe.copy(deep=True)
    mapping_result = map_columns(list(dataframe.columns))

    corrected = apply_project_assignment(
        dataframe,
        mapping_result,
        "4G Saturation",
    )

    assert corrected["Project"].tolist() == ["4G Saturation"]
    pd.testing.assert_frame_equal(dataframe, original)


def test_project_assignment_cannot_overwrite_existing_project_values() -> None:
    dataframe = pd.DataFrame({"Project": ["LWE"]})
    mapping_result = map_columns(list(dataframe.columns))

    with pytest.raises(ValueError, match="only when Project is missing"):
        apply_project_assignment(
            dataframe,
            mapping_result,
            "4G Saturation",
        )

    assert dataframe["Project"].tolist() == ["LWE"]


@pytest.mark.parametrize(
    "circle",
    [
        "4G Satu",
        "North 4g-saturation Circle",
        "North 4G---SATURATION Circle",
        "North 4 G Satu Circle",
    ],
)
def test_circle_variants_automatically_assign_4g_saturation(
    circle: str,
) -> None:
    dataframe = pd.DataFrame({"Circle": [circle]})
    original = dataframe.copy(deep=True)
    mapping_result = map_columns(list(dataframe.columns))

    assignment = apply_circle_project_assignment(dataframe, mapping_result)
    validated = validate_project_identity(
        assignment.dataframe,
        map_columns(list(assignment.dataframe.columns)),
    )

    assert assignment.assigned_row_positions == (1,)
    assert assignment.dataframe["Project"].tolist() == ["4G Saturation"]
    assert validated.status is ProjectIdentityStatus.VALID
    assert validated.project == "4G Saturation"
    pd.testing.assert_frame_equal(dataframe, original)


@pytest.mark.parametrize("circle", ["North", "LWE", None, ""])
def test_unrelated_or_missing_circle_does_not_assign_a_project(
    circle: object,
) -> None:
    dataframe = pd.DataFrame({"Circle": [circle]})
    assignment = apply_circle_project_assignment(
        dataframe,
        map_columns(list(dataframe.columns)),
    )

    assert assignment.assigned_row_positions == ()
    assert "Project" not in assignment.dataframe.columns
    assert "Project" not in dataframe.columns


def test_circle_assignment_fills_only_blank_project_rows() -> None:
    dataframe = pd.DataFrame(
        {
            "Circle": ["4G-Satu North", "4G Satu South", "North"],
            "Project": [None, None, None],
        }
    )
    original = dataframe.copy(deep=True)
    assignment = apply_circle_project_assignment(
        dataframe,
        map_columns(list(dataframe.columns)),
    )

    assert assignment.assigned_row_positions == (1, 2)
    assert assignment.dataframe["Project"].iloc[0] == "4G Saturation"
    assert assignment.dataframe["Project"].iloc[1] == "4G Saturation"
    assert pd.isna(assignment.dataframe["Project"].iloc[2])
    assert validate_project_identity(
        assignment.dataframe,
        map_columns(list(assignment.dataframe.columns)),
    ).status is ProjectIdentityStatus.MISSING_VALUES
    pd.testing.assert_frame_equal(dataframe, original)


def test_circle_assignment_does_not_replace_existing_project_values() -> None:
    dataframe = pd.DataFrame(
        {"Circle": ["4G-Satu North"], "Project": ["LWE"]}
    )

    assignment = apply_circle_project_assignment(
        dataframe,
        map_columns(list(dataframe.columns)),
    )

    assert assignment.assigned_row_positions == ()
    assert assignment.dataframe["Project"].tolist() == ["LWE"]


def test_circle_assignment_does_not_bypass_project_or_circle_mapping_approval() -> None:
    fuzzy_circle = pd.DataFrame({"Circl": ["4G Satu North"]})
    unapproved_circle_result = apply_circle_project_assignment(
        fuzzy_circle,
        map_columns(list(fuzzy_circle.columns)),
    )
    unsupported_project = pd.DataFrame(
        {"Circle": ["4G Satu North"], "Project": ["4G-Saturation"]}
    )
    unsupported_project_result = apply_circle_project_assignment(
        unsupported_project,
        map_columns(list(unsupported_project.columns)),
    )

    assert unapproved_circle_result.assigned_row_positions == ()
    assert "Project" not in unapproved_circle_result.dataframe.columns
    assert unsupported_project_result.assigned_row_positions == ()
    assert unsupported_project_result.dataframe["Project"].tolist() == [
        "4G-Saturation"
    ]
    assert suggest_project_value_corrections(
        unsupported_project_result.dataframe,
        map_columns(list(unsupported_project.columns)),
    )


def test_manual_assignment_can_fill_only_remaining_blank_project_values() -> None:
    dataframe = pd.DataFrame({"Project": ["4G Saturation", None]})
    mapping_result = map_columns(list(dataframe.columns))

    corrected = apply_project_assignment(
        dataframe,
        mapping_result,
        "4G Saturation",
    )

    assert corrected["Project"].tolist() == ["4G Saturation", "4G Saturation"]
    assert dataframe["Project"].iloc[0] == "4G Saturation"
    assert pd.isna(dataframe["Project"].iloc[1])


def test_project_correction_changes_only_the_recognized_value_in_a_copy() -> None:
    dataframe = pd.DataFrame({"Project": ["4G-Saturation", "LWE", "Other"]})
    original = dataframe.copy(deep=True)
    mapping_result = map_columns(list(dataframe.columns))
    suggestions = suggest_project_value_corrections(dataframe, mapping_result)

    corrected = apply_project_value_corrections(
        dataframe,
        mapping_result,
        {"4G-Saturation": "4G Saturation"},
    )

    assert suggestions[0].row_positions == (1,)
    assert corrected["Project"].tolist() == ["4G Saturation", "LWE", "Other"]
    pd.testing.assert_frame_equal(dataframe, original)


def test_project_correction_rejects_unexpected_values() -> None:
    dataframe = pd.DataFrame({"Project": ["Unknown"]})
    mapping_result = map_columns(list(dataframe.columns))

    with pytest.raises(ValueError, match="not a currently suggested value"):
        apply_project_value_corrections(
            dataframe,
            mapping_result,
            {"Unknown": "LWE"},
        )
