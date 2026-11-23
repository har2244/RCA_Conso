"""Combine cleaned RCA DataFrames and remove batch-wide exact duplicates."""

from typing import Sequence

import pandas as pd

from config.column_schema import MANDATORY_COLUMNS
from rca_consolidator.processing.duplicate_handler import (
    DuplicateRemovalResult,
    remove_exact_duplicates,
)


def consolidate_dataframes(
    dataframes: Sequence[pd.DataFrame],
) -> DuplicateRemovalResult:
    """Concatenate schema-standardized frames and deduplicate them once.

    The sequence order and each DataFrame's row order determine which duplicate
    occurrence is retained first. Input DataFrames are not modified.
    """
    frames = list(dataframes)
    for frame_index, dataframe in enumerate(frames):
        if tuple(dataframe.columns) != MANDATORY_COLUMNS:
            raise ValueError(
                f"DataFrame at position {frame_index} does not have exactly "
                "the mandatory columns in schema order."
            )

    combined = (
        pd.concat(frames, axis=0, sort=False)
        if frames
        else pd.DataFrame(columns=MANDATORY_COLUMNS)
    )
    return remove_exact_duplicates(combined)