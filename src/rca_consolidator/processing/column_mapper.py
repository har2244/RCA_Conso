"""Suggest safe and fuzzy mappings from uploaded column names to the RCA schema."""

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, replace
from enum import Enum
from typing import Hashable, Mapping, Sequence

import pandas as pd
from rapidfuzz import fuzz

from config.column_schema import (
    FUZZY_AMBIGUITY_MARGIN,
    FUZZY_MATCH_THRESHOLD,
    MANDATORY_COLUMNS,
)


class MappingStatus(str, Enum):
    """Lifecycle state for one source-column mapping."""

    EXACT_MATCH = "EXACT_MATCH"
    NORMALIZED_MATCH = "NORMALIZED_MATCH"
    SUGGESTED = "SUGGESTED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    AMBIGUOUS = "AMBIGUOUS"
    MISSING = "MISSING"


@dataclass(frozen=True)
class ColumnMapping:
    """Mapping details for a source column or a missing standard column."""

    source_index: int | None
    original_column: Hashable | None
    target_column: str | None
    similarity_score: float | None
    status: MappingStatus | None
    user_approved: bool | None = None
    candidate_targets: tuple[str, ...] = ()
    candidate_scores: tuple[tuple[str, float], ...] = ()


@dataclass(frozen=True)
class ColumnMappingResult:
    """Auditable mapping outcome for one workbook's source columns."""

    workbook_name: str | None
    mappings: tuple[ColumnMapping, ...]
    unexpected_columns: tuple[Hashable, ...]
    duplicate_source_columns: tuple[Hashable, ...]
    missing_columns: tuple[str, ...]
    conflicting_targets: tuple[str, ...]

    @property
    def suggestions(self) -> tuple[ColumnMapping, ...]:
        """Return fuzzy suggestions and mappings that need manual resolution."""
        return tuple(
            mapping
            for mapping in self.mappings
            if mapping.status in (MappingStatus.SUGGESTED, MappingStatus.AMBIGUOUS)
        )


class MappingConflictError(ValueError):
    """Raised when explicit mapping decisions still assign a target more than once."""


def _normalize_column_name(name: str) -> str:
    """Normalize harmless casing, spacing, underscore, and punctuation differences."""
    expanded = unicodedata.normalize("NFKC", name)
    expanded = expanded.replace("_", " ")
    expanded = re.sub(r"[^\w\s]", " ", expanded)
    return " ".join(expanded.casefold().split())


def _validate_options(threshold: float, ambiguity_margin: float) -> None:
    if not 0 <= threshold <= 100:
        raise ValueError("fuzzy_threshold must be between 0 and 100.")
    if not 0 <= ambiguity_margin <= 100:
        raise ValueError("ambiguity_margin must be between 0 and 100.")


def _find_duplicate_columns(columns: Sequence[Hashable]) -> tuple[Hashable, ...]:
    counts = Counter(columns)
    seen: set[Hashable] = set()
    duplicates: list[Hashable] = []
    for column in columns:
        if counts[column] > 1 and column not in seen:
            duplicates.append(column)
            seen.add(column)
    return tuple(duplicates)


def _refresh_mapping_result(
    workbook_name: str | None,
    source_mappings: Sequence[ColumnMapping],
    unexpected_columns: Sequence[Hashable],
    duplicate_source_columns: Sequence[Hashable],
) -> ColumnMappingResult:
    mappings = list(source_mappings)
    candidates_by_target: dict[str, list[int]] = {
        target: [] for target in MANDATORY_COLUMNS
    }

    for mapping_index, mapping in enumerate(mappings):
        if mapping.source_index is None or mapping.status is MappingStatus.REJECTED:
            continue
        for target in mapping.candidate_targets:
            candidates_by_target[target].append(mapping_index)

    conflicting_targets = tuple(
        target for target in MANDATORY_COLUMNS if len(candidates_by_target[target]) > 1
    )
    for target in conflicting_targets:
        mapping_indexes = candidates_by_target[target]
        approved_indexes = [
            index
            for index in mapping_indexes
            if mappings[index].status is MappingStatus.APPROVED
        ]
        if len(approved_indexes) > 1:
            raise MappingConflictError(
                f"Multiple source columns were approved for '{target}'."
            )

        exact_indexes = [
            index
            for index in mapping_indexes
            if mappings[index].status is MappingStatus.EXACT_MATCH
        ]
        normalized_indexes = [
            index
            for index in mapping_indexes
            if mappings[index].status is MappingStatus.NORMALIZED_MATCH
        ]
        if exact_indexes:
            preferred_indexes = exact_indexes
        elif len(normalized_indexes) == 1:
            preferred_indexes = normalized_indexes
        else:
            preferred_indexes = []

        for index in mapping_indexes:
            mapping = mappings[index]
            if (
                index not in preferred_indexes
                and mapping.status
                not in (MappingStatus.APPROVED, MappingStatus.REJECTED)
            ):
                mappings[index] = replace(
                    mapping,
                    target_column=target if len(mapping.candidate_targets) == 1 else None,
                    status=MappingStatus.AMBIGUOUS,
                    user_approved=None,
                )

    missing_columns = tuple(
        target
        for target in MANDATORY_COLUMNS
        if not candidates_by_target[target]
    )
    mappings.extend(
        ColumnMapping(
            source_index=None,
            original_column=None,
            target_column=target,
            similarity_score=None,
            status=MappingStatus.MISSING,
        )
        for target in missing_columns
    )
    return ColumnMappingResult(
        workbook_name=workbook_name,
        mappings=tuple(mappings),
        unexpected_columns=tuple(unexpected_columns),
        duplicate_source_columns=tuple(duplicate_source_columns),
        missing_columns=missing_columns,
        conflicting_targets=conflicting_targets,
    )


def map_columns(
    source_columns: Sequence[Hashable],
    workbook_name: str | None = None,
    *,
    fuzzy_threshold: float | None = None,
    ambiguity_margin: float | None = None,
) -> ColumnMappingResult:
    """Match source headers to the canonical schema without applying fuzzy matches."""
    threshold = FUZZY_MATCH_THRESHOLD if fuzzy_threshold is None else fuzzy_threshold
    margin = FUZZY_AMBIGUITY_MARGIN if ambiguity_margin is None else ambiguity_margin
    _validate_options(threshold, margin)

    normalized_targets = {
        target: _normalize_column_name(target) for target in MANDATORY_COLUMNS
    }
    source_mappings: list[ColumnMapping] = []
    unexpected_columns: list[Hashable] = []

    for source_index, source_column in enumerate(source_columns):
        if not isinstance(source_column, str):
            source_mappings.append(
                ColumnMapping(
                    source_index=source_index,
                    original_column=source_column,
                    target_column=None,
                    similarity_score=None,
                    status=None,
                )
            )
            unexpected_columns.append(source_column)
            continue

        if source_column in MANDATORY_COLUMNS:
            source_mappings.append(
                ColumnMapping(
                    source_index=source_index,
                    original_column=source_column,
                    target_column=source_column,
                    similarity_score=100.0,
                    status=MappingStatus.EXACT_MATCH,
                    candidate_targets=(source_column,),
                    candidate_scores=((source_column, 100.0),),
                )
            )
            continue

        normalized_source = _normalize_column_name(source_column)
        normalized_matches = tuple(
            target
            for target, normalized_target in normalized_targets.items()
            if normalized_source == normalized_target
        )
        if normalized_matches:
            target = normalized_matches[0]
            source_mappings.append(
                ColumnMapping(
                    source_index=source_index,
                    original_column=source_column,
                    target_column=target,
                    similarity_score=100.0,
                    status=MappingStatus.NORMALIZED_MATCH,
                    candidate_targets=(target,),
                    candidate_scores=((target, 100.0),),
                )
            )
            continue

        scores = sorted(
            (
                (target, fuzz.ratio(normalized_source, normalized_target))
                for target, normalized_target in normalized_targets.items()
            ),
            key=lambda item: (-item[1], MANDATORY_COLUMNS.index(item[0])),
        )
        best_score = scores[0][1]
        candidate_scores = tuple(
            (target, float(score))
            for target, score in scores
            if score >= threshold and best_score - score <= margin
        )
        if not candidate_scores:
            source_mappings.append(
                ColumnMapping(
                    source_index=source_index,
                    original_column=source_column,
                    target_column=None,
                    similarity_score=None,
                    status=None,
                )
            )
            unexpected_columns.append(source_column)
            continue

        candidate_targets = tuple(target for target, _ in candidate_scores)
        is_ambiguous = len(candidate_targets) > 1
        source_mappings.append(
            ColumnMapping(
                source_index=source_index,
                original_column=source_column,
                target_column=None if is_ambiguous else candidate_targets[0],
                similarity_score=candidate_scores[0][1],
                status=(
                    MappingStatus.AMBIGUOUS
                    if is_ambiguous
                    else MappingStatus.SUGGESTED
                ),
                candidate_targets=candidate_targets,
                candidate_scores=candidate_scores,
            )
        )

    return _refresh_mapping_result(
        workbook_name=workbook_name,
        source_mappings=source_mappings,
        unexpected_columns=unexpected_columns,
        duplicate_source_columns=_find_duplicate_columns(source_columns),
    )


def apply_mapping_decisions(
    mapping_result: ColumnMappingResult,
    decisions: Mapping[int, str | None],
) -> ColumnMappingResult:
    """Record explicit approvals or rejections by source-column position.

    A target name approves that target; `None` rejects the proposed mapping.
    """
    mappings = list(mapping_result.mappings)
    source_mapping_indexes = {
        mapping.source_index: index
        for index, mapping in enumerate(mappings)
        if mapping.source_index is not None
    }

    for source_index, target in decisions.items():
        if source_index not in source_mapping_indexes:
            raise ValueError(f"No source column exists at index {source_index}.")
        mapping_index = source_mapping_indexes[source_index]
        mapping = mappings[mapping_index]
        if mapping.status not in (
            MappingStatus.SUGGESTED,
            MappingStatus.AMBIGUOUS,
            MappingStatus.APPROVED,
        ):
            raise ValueError(
                f"Source column at index {source_index} does not need a decision."
            )
        if target is None:
            mappings[mapping_index] = replace(
                mapping,
                status=MappingStatus.REJECTED,
                user_approved=False,
            )
            continue
        if target not in mapping.candidate_targets:
            raise ValueError(
                f"'{target}' is not a candidate target for source column "
                f"at index {source_index}."
            )
        selected_score = next(
            (
                score
                for candidate, score in mapping.candidate_scores
                if candidate == target
            ),
            mapping.similarity_score,
        )
        mappings[mapping_index] = replace(
            mapping,
            target_column=target,
            similarity_score=selected_score,
            status=MappingStatus.APPROVED,
            user_approved=True,
            candidate_targets=(target,),
        )

    return _refresh_mapping_result(
        workbook_name=mapping_result.workbook_name,
        source_mappings=[
            mapping for mapping in mappings if mapping.source_index is not None
        ],
        unexpected_columns=mapping_result.unexpected_columns,
        duplicate_source_columns=mapping_result.duplicate_source_columns,
    )


def apply_approved_mappings(
    dataframe: pd.DataFrame,
    mapping_result: ColumnMappingResult,
) -> pd.DataFrame:
    """Return a copy with exact, normalized, and explicitly approved names applied."""
    if mapping_result.conflicting_targets:
        targets = ", ".join(mapping_result.conflicting_targets)
        raise MappingConflictError(
            f"Conflicting source columns need resolution for: {targets}."
        )

    source_mappings = sorted(
        (
            mapping
            for mapping in mapping_result.mappings
            if mapping.source_index is not None
        ),
        key=lambda mapping: mapping.source_index,
    )
    if len(source_mappings) != len(dataframe.columns):
        raise ValueError("The mapping result does not match the DataFrame columns.")
    for mapping in source_mappings:
        if dataframe.columns[mapping.source_index] != mapping.original_column:
            raise ValueError("The mapping result was created for different columns.")

    applied_targets: set[str] = set()
    renamed_columns = list(dataframe.columns)
    applicable_statuses = {
        MappingStatus.EXACT_MATCH,
        MappingStatus.NORMALIZED_MATCH,
        MappingStatus.APPROVED,
    }
    for mapping in source_mappings:
        if mapping.status not in applicable_statuses or mapping.target_column is None:
            continue
        if mapping.target_column in applied_targets:
            raise MappingConflictError(
                f"Multiple source columns would map to '{mapping.target_column}'."
            )
        applied_targets.add(mapping.target_column)
        renamed_columns[mapping.source_index] = mapping.target_column

    result = dataframe.copy(deep=True)
    result.columns = renamed_columns
    return result