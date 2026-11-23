"""Tests for mandatory schema validation."""

import pandas as pd

from config.column_schema import MANDATORY_COLUMNS
from rca_consolidator.processing.column_mapper import (
    MappingStatus,
    apply_mapping_decisions,
)
from rca_consolidator.validation.schema_validator import (
    SchemaStatus,
    validate_dataframe_schema,
)


def test_accepts_all_mandatory_columns_and_reports_exact_matches() -> None:
    result = validate_dataframe_schema(pd.DataFrame(columns=MANDATORY_COLUMNS))

    assert result.status is SchemaStatus.VALID
    assert result.is_valid
    assert result.missing_columns == ()
    assert all(
        mapping.status is MappingStatus.EXACT_MATCH
        for mapping in result.mapping_result.mappings
    )


def test_missing_mandatory_column_invalidates_schema() -> None:
    columns = [column for column in MANDATORY_COLUMNS if column != "RCA"]

    result = validate_dataframe_schema(pd.DataFrame(columns=columns))

    assert result.status is SchemaStatus.INVALID
    assert result.missing_columns == ("RCA",)


def test_spelling_suggestion_requires_approval() -> None:
    columns = list(MANDATORY_COLUMNS)
    columns[1] = "Projec"
    result = validate_dataframe_schema(pd.DataFrame(columns=columns))

    assert result.status is SchemaStatus.REVIEW_REQUIRED
    assert result.requires_review
    assert result.missing_columns == ()
    suggestion = next(
        mapping
        for mapping in result.mapping_result.mappings
        if mapping.original_column == "Projec"
    )
    assert suggestion.target_column == "Project"
    assert suggestion.user_approved is None


def test_fuzzy_competitor_to_exact_match_requires_manual_review() -> None:
    columns = [*MANDATORY_COLUMNS, "Projec"]
    result = validate_dataframe_schema(pd.DataFrame(columns=columns))

    assert result.status is SchemaStatus.REVIEW_REQUIRED
    assert result.conflicting_targets == ("Project",)
    assert result.mapping_result.mappings[1].status is MappingStatus.EXACT_MATCH
    assert result.mapping_result.mappings[-1].status is MappingStatus.AMBIGUOUS


def test_approved_suggestion_completes_schema_validation() -> None:
    columns = list(MANDATORY_COLUMNS)
    columns[1] = "Projec"
    dataframe = pd.DataFrame(columns=columns)
    initial = validate_dataframe_schema(dataframe)
    resolved_mappings = apply_mapping_decisions(initial.mapping_result, {1: "Project"})

    result = validate_dataframe_schema(dataframe, mapping_result=resolved_mappings)

    assert result.status is SchemaStatus.VALID
    assert result.missing_columns == ()


def test_extra_columns_are_reported_but_not_required() -> None:
    columns = [*MANDATORY_COLUMNS, "Source Note"]

    result = validate_dataframe_schema(pd.DataFrame(columns=columns))

    assert result.status is SchemaStatus.VALID
    assert result.unexpected_columns == ("Source Note",)
    assert result.missing_columns == ()


def test_duplicate_source_column_names_are_reported_for_review() -> None:
    columns = [*MANDATORY_COLUMNS, "Site ID"]

    result = validate_dataframe_schema(pd.DataFrame(columns=columns))

    assert "Site ID" in result.duplicate_source_columns
    assert "Site ID" in result.conflicting_targets
    assert result.status is SchemaStatus.REVIEW_REQUIRED


def test_rejected_suggestion_becomes_a_missing_mandatory_column() -> None:
    columns = list(MANDATORY_COLUMNS)
    columns[1] = "Projec"
    dataframe = pd.DataFrame(columns=columns)
    initial = validate_dataframe_schema(dataframe)
    resolved_mappings = apply_mapping_decisions(initial.mapping_result, {1: None})

    result = validate_dataframe_schema(dataframe, mapping_result=resolved_mappings)

    assert result.status is SchemaStatus.INVALID
    assert result.missing_columns == ("Project",)


def test_rejected_only_suggestion_is_missing_but_approval_resolves_it() -> None:
    columns = [column for column in MANDATORY_COLUMNS if column != "Project"]
    columns.insert(1, "Projec")
    dataframe = pd.DataFrame(columns=columns)
    initial = validate_dataframe_schema(dataframe)

    rejected = apply_mapping_decisions(initial.mapping_result, {1: None})
    rejected_validation = validate_dataframe_schema(
        dataframe, mapping_result=rejected
    )
    assert rejected_validation.status is SchemaStatus.INVALID
    assert rejected_validation.missing_columns == ("Project",)

    approved = apply_mapping_decisions(initial.mapping_result, {1: "Project"})
    approved_validation = validate_dataframe_schema(
        dataframe, mapping_result=approved
    )
    assert approved_validation.status is SchemaStatus.VALID
    assert approved_validation.missing_columns == ()
