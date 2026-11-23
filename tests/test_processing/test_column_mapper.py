"""Tests for schema-driven column mapping and user approval."""

import pandas as pd
import pytest

from config.column_schema import MANDATORY_COLUMNS
from rca_consolidator.processing.column_mapper import (
    MappingConflictError,
    MappingStatus,
    apply_approved_mappings,
    apply_mapping_decisions,
    map_columns,
)


def test_exact_schema_columns_match_in_order() -> None:
    result = map_columns(MANDATORY_COLUMNS, workbook_name="circle.xlsx")

    assert result.workbook_name == "circle.xlsx"
    assert result.missing_columns == ()
    assert [mapping.status for mapping in result.mappings] == [
        MappingStatus.EXACT_MATCH
    ] * len(MANDATORY_COLUMNS)


def test_single_spelling_mistake_is_only_suggested() -> None:
    result = map_columns(["Projec"])

    mapping = result.mappings[0]
    assert mapping.original_column == "Projec"
    assert mapping.target_column == "Project"
    assert mapping.status is MappingStatus.SUGGESTED
    assert mapping.similarity_score is not None
    assert mapping.user_approved is None


def test_multiple_spelling_mistakes_are_suggested() -> None:
    result = map_columns(["Projec", "Circl", "Siet ID"])

    assert [mapping.target_column for mapping in result.mappings[:3]] == [
        "Project",
        "Circle",
        "Site ID",
    ]
    assert all(
        mapping.status is MappingStatus.SUGGESTED
        for mapping in result.mappings[:3]
    )


@pytest.mark.parametrize(
    ("source", "expected_status", "target"),
    [
        ("pRoJeCt", MappingStatus.NORMALIZED_MATCH, "Project"),
        ("  Site Name  ", MappingStatus.NORMALIZED_MATCH, "Site Name"),
        ("Site_Name", MappingStatus.NORMALIZED_MATCH, "Site Name"),
        ("Outage Min", MappingStatus.NORMALIZED_MATCH, "Outage Min."),
        ("O&M Start Yes No", MappingStatus.NORMALIZED_MATCH, "O&M Start (Yes/No)"),
    ],
)
def test_harmless_formatting_variations_match_safely(
    source: str,
    expected_status: MappingStatus,
    target: str,
) -> None:
    result = map_columns([source])

    assert result.mappings[0].target_column == target
    assert result.mappings[0].status is expected_status


def test_ambiguous_fuzzy_match_is_flagged_for_manual_review() -> None:
    result = map_columns(
        ["Bucket"],
        fuzzy_threshold=60,
        ambiguity_margin=30,
    )

    mapping = result.mappings[0]
    assert mapping.status is MappingStatus.AMBIGUOUS
    assert "Final Bucket" in mapping.candidate_targets
    assert "Bucket - 2" in mapping.candidate_targets


def test_two_sources_suggesting_same_target_are_conflicting() -> None:
    result = map_columns(["Projec", "Projectt"])

    assert result.conflicting_targets == ("Project",)
    assert [mapping.status for mapping in result.mappings[:2]] == [
        MappingStatus.AMBIGUOUS,
        MappingStatus.AMBIGUOUS,
    ]
    assert all(mapping.target_column == "Project" for mapping in result.mappings[:2])


def test_exact_match_is_not_downgraded_by_a_competing_fuzzy_suggestion() -> None:
    result = map_columns(["Project", "Projec"])

    assert result.conflicting_targets == ("Project",)
    assert result.mappings[0].status is MappingStatus.EXACT_MATCH
    assert result.mappings[1].status is MappingStatus.AMBIGUOUS
    assert result.suggestions == (result.mappings[1],)


def test_multiple_exact_sources_are_a_blocking_conflict() -> None:
    result = map_columns(["Project", "Project"])

    assert result.conflicting_targets == ("Project",)
    source_mappings = [
        mapping for mapping in result.mappings if mapping.source_index is not None
    ]
    assert [mapping.status for mapping in source_mappings] == [
        MappingStatus.EXACT_MATCH,
        MappingStatus.EXACT_MATCH,
    ]
    with pytest.raises(MappingConflictError, match="need resolution"):
        apply_approved_mappings(pd.DataFrame(columns=["Project", "Project"]), result)


def test_normalized_match_outranks_but_does_not_hide_fuzzy_conflict() -> None:
    result = map_columns(["pRoJeCt", "Projec"])

    assert result.conflicting_targets == ("Project",)
    assert result.mappings[0].status is MappingStatus.NORMALIZED_MATCH
    assert result.mappings[1].status is MappingStatus.AMBIGUOUS
    with pytest.raises(MappingConflictError, match="need resolution"):
        apply_approved_mappings(
            pd.DataFrame(columns=["pRoJeCt", "Projec"]), result
        )


def test_rejecting_competing_normalized_source_resolves_exact_target() -> None:
    result = map_columns(["Site ID", "Site Id"])

    assert result.mappings[0].status is MappingStatus.EXACT_MATCH
    assert result.mappings[1].status is MappingStatus.AMBIGUOUS
    resolved = apply_mapping_decisions(result, {1: None})

    assert resolved.conflicting_targets == ()
    assert resolved.mappings[0].status is MappingStatus.EXACT_MATCH
    assert resolved.mappings[1].status is MappingStatus.REJECTED
    assert "Site ID" not in resolved.missing_columns


def test_approves_and_applies_suggested_mapping_without_mutating_source() -> None:
    source = pd.DataFrame({"Projec": ["LTE"], "Site ID": ["00123"]})
    result = map_columns(list(source.columns))
    approved = apply_mapping_decisions(result, {0: "Project"})

    mapped = apply_approved_mappings(source, approved)

    assert list(mapped.columns) == ["Project", "Site ID"]
    assert mapped.loc[0, "Project"] == "LTE"
    assert mapped.loc[0, "Site ID"] == "00123"
    pd.testing.assert_frame_equal(
        source,
        pd.DataFrame({"Projec": ["LTE"], "Site ID": ["00123"]}),
    )


def test_rejected_mapping_is_not_applied() -> None:
    source = pd.DataFrame({"Projec": ["LTE"]})
    result = map_columns(list(source.columns))
    rejected = apply_mapping_decisions(result, {0: None})

    mapped = apply_approved_mappings(source, rejected)

    assert list(mapped.columns) == ["Projec"]
    assert rejected.mappings[0].status is MappingStatus.REJECTED
    assert rejected.mappings[0].user_approved is False


def test_unapproved_suggestion_is_never_applied() -> None:
    source = pd.DataFrame({"Projec": ["LTE"]})
    result = map_columns(list(source.columns))

    mapped = apply_approved_mappings(source, result)

    assert list(mapped.columns) == ["Projec"]
    assert result.mappings[0].status is MappingStatus.SUGGESTED


def test_mapping_result_must_match_dataframe_columns() -> None:
    source = pd.DataFrame({"Projec": ["LTE"]})
    other = pd.DataFrame({"Project": ["LTE"]})
    result = map_columns(list(source.columns))

    with pytest.raises(ValueError, match="different columns"):
        apply_approved_mappings(other, result)


def test_duplicate_headers_keep_original_positions_and_names() -> None:
    source = pd.DataFrame([["001", "002"]], columns=["Site ID", "Site ID"])
    result = map_columns(list(source.columns))

    assert result.duplicate_source_columns == ("Site ID",)
    assert [
        (mapping.source_index, mapping.original_column)
        for mapping in result.mappings
        if mapping.source_index is not None
    ] == [(0, "Site ID"), (1, "Site ID")]
    pd.testing.assert_frame_equal(
        source,
        pd.DataFrame([["001", "002"]], columns=["Site ID", "Site ID"]),
    )
