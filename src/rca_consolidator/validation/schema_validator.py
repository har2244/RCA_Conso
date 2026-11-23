"""Validate uploaded worksheet headers against the centralized RCA schema."""

from dataclasses import dataclass
from enum import Enum
from typing import Hashable

import pandas as pd

from config.column_schema import FUZZY_AMBIGUITY_MARGIN, FUZZY_MATCH_THRESHOLD
from rca_consolidator.processing.column_mapper import (
    ColumnMappingResult,
    map_columns,
)


class SchemaStatus(str, Enum):
    """Overall schema validation state."""

    VALID = "VALID"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    INVALID = "INVALID"


@dataclass(frozen=True)
class SchemaValidationResult:
    """Structured validation details for one worksheet."""

    workbook_name: str | None
    status: SchemaStatus
    mapping_result: ColumnMappingResult
    missing_columns: tuple[str, ...]
    unexpected_columns: tuple[Hashable, ...]
    duplicate_source_columns: tuple[Hashable, ...]
    conflicting_targets: tuple[str, ...]

    @property
    def is_valid(self) -> bool:
        """Return whether the schema is ready without further user review."""
        return self.status is SchemaStatus.VALID

    @property
    def requires_review(self) -> bool:
        """Return whether suggestions or source-column issues need manual review."""
        return self.status is SchemaStatus.REVIEW_REQUIRED


def _verify_mapping_matches_dataframe(
    dataframe: pd.DataFrame,
    mapping_result: ColumnMappingResult,
) -> None:
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


def validate_dataframe_schema(
    dataframe: pd.DataFrame,
    workbook_name: str | None = None,
    *,
    mapping_result: ColumnMappingResult | None = None,
    fuzzy_threshold: float | None = None,
    ambiguity_margin: float | None = None,
) -> SchemaValidationResult:
    """Validate mandatory headers while distinguishing missing, extra, and review cases."""
    if mapping_result is None:
        mapping_result = map_columns(
            list(dataframe.columns),
            workbook_name=workbook_name,
            fuzzy_threshold=(
                FUZZY_MATCH_THRESHOLD if fuzzy_threshold is None else fuzzy_threshold
            ),
            ambiguity_margin=(
                FUZZY_AMBIGUITY_MARGIN
                if ambiguity_margin is None
                else ambiguity_margin
            ),
        )
    else:
        _verify_mapping_matches_dataframe(dataframe, mapping_result)

    if mapping_result.missing_columns:
        status = SchemaStatus.INVALID
    elif (
        mapping_result.suggestions
        or mapping_result.duplicate_source_columns
        or mapping_result.conflicting_targets
    ):
        status = SchemaStatus.REVIEW_REQUIRED
    else:
        status = SchemaStatus.VALID

    return SchemaValidationResult(
        workbook_name=(
            workbook_name
            if workbook_name is not None
            else mapping_result.workbook_name
        ),
        status=status,
        mapping_result=mapping_result,
        missing_columns=mapping_result.missing_columns,
        unexpected_columns=mapping_result.unexpected_columns,
        duplicate_source_columns=mapping_result.duplicate_source_columns,
        conflicting_targets=mapping_result.conflicting_targets,
    )