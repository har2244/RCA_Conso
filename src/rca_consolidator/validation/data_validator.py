"""Validate standardized RCA cell values without changing the DataFrame."""

from dataclasses import dataclass
from typing import Hashable

import pandas as pd

from config.column_schema import MANDATORY_COLUMNS
from rca_consolidator.ingestion.excel_reader import (
    SITE_ID_FORMAT_FINDINGS_ATTR,
    SiteIdFormatFinding,
)
from rca_consolidator.processing.data_cleaner import (
    is_blank_value,
    is_supported_iso_date,
)


@dataclass(frozen=True)
class BlankCellIssue:
    """A blank mandatory cell identified by row position and column name."""

    row_position: int
    dataframe_index: Hashable
    column: str


@dataclass(frozen=True)
class DateValueIssue:
    """A nonblank Date value that was not safely normalized as ISO 8601."""

    row_position: int
    dataframe_index: Hashable
    value: object


@dataclass(frozen=True)
class DataValidationResult:
    """Cell-level findings for a standardized RCA DataFrame."""

    blank_cells: tuple[BlankCellIssue, ...]
    unsupported_dates: tuple[DateValueIssue, ...]
    site_id_format_findings: tuple[SiteIdFormatFinding, ...] = ()

    @property
    def is_valid(self) -> bool:
        """Return whether there are no blank mandatory cells or unsupported dates."""
        return not self.blank_cells and not self.unsupported_dates

    @property
    def requires_review(self) -> bool:
        """Return whether Site ID formatting findings need review."""
        return bool(self.site_id_format_findings)


def validate_cleaned_dataframe(dataframe: pd.DataFrame) -> DataValidationResult:
    """Report blank mandatory cells and unsupported dates in cleaned records.

    This validator expects canonical columns in the exact schema order. Missing
    or misordered columns are schema errors and must be handled separately.
    """
    if tuple(dataframe.columns) != MANDATORY_COLUMNS:
        raise ValueError(
            "Data validation requires exactly the mandatory columns in schema order."
        )

    site_id_format_findings = dataframe.attrs.get(
        SITE_ID_FORMAT_FINDINGS_ATTR,
        (),
    )
    if not isinstance(site_id_format_findings, tuple) or any(
        not isinstance(finding, SiteIdFormatFinding)
        for finding in site_id_format_findings
    ):
        raise ValueError("The DataFrame contains invalid Site ID format findings.")

    blank_cells: list[BlankCellIssue] = []
    unsupported_dates: list[DateValueIssue] = []
    for row_position, dataframe_index in enumerate(dataframe.index):
        for column in MANDATORY_COLUMNS:
            if is_blank_value(dataframe[column].iloc[row_position]):
                blank_cells.append(
                    BlankCellIssue(
                        row_position=row_position,
                        dataframe_index=dataframe_index,
                        column=column,
                    )
                )
        date_value = dataframe["Date"].iloc[row_position]
        if not is_blank_value(date_value) and not is_supported_iso_date(date_value):
            unsupported_dates.append(
                DateValueIssue(
                    row_position=row_position,
                    dataframe_index=dataframe_index,
                    value=date_value,
                )
            )

    return DataValidationResult(
        blank_cells=tuple(blank_cells),
        unsupported_dates=tuple(unsupported_dates),
        site_id_format_findings=site_id_format_findings,
    )