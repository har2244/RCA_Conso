"""Remove exact duplicate RCA records from a combined standardized dataset."""

from dataclasses import dataclass

import pandas as pd

from config.column_schema import MANDATORY_COLUMNS


@dataclass(frozen=True)
class DuplicateRemovalResult:
    """Deduplication output and the number of duplicate rows removed."""

    deduplicated_dataframe: pd.DataFrame
    duplicates_detected: int
    duplicates_removed: int


def remove_exact_duplicates(dataframe: pd.DataFrame) -> DuplicateRemovalResult:
    """Keep the first row for each exact match across all mandatory columns.

    Pass one standardized DataFrame containing records from all uploaded files.
    The input is not normalized or modified.
    """
    if tuple(dataframe.columns) != MANDATORY_COLUMNS:
        raise ValueError(
            "Duplicate detection requires exactly the mandatory columns "
            "in schema order."
        )

    duplicate_rows = dataframe.duplicated(
        subset=list(MANDATORY_COLUMNS),
        keep="first",
    )
    duplicate_count = int(duplicate_rows.sum())
    retained = dataframe.loc[~duplicate_rows].copy(deep=True)

    return DuplicateRemovalResult(
        deduplicated_dataframe=retained,
        duplicates_detected=duplicate_count,
        duplicates_removed=duplicate_count,
    )