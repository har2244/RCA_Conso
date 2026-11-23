"""Tests for batch consolidation and duplicate removal."""

import pandas as pd
import pytest

from config.column_schema import MANDATORY_COLUMNS
import rca_consolidator.processing.consolidation_engine as consolidation_engine
from rca_consolidator.processing.consolidation_engine import (
    consolidate_dataframes,
)


def _row(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        column: f"value-{index}" for index, column in enumerate(MANDATORY_COLUMNS)
    }
    values.update(overrides)
    return values


def test_consolidates_multiple_frames_in_order_and_deduplicates_across_them() -> None:
    first = pd.DataFrame([_row(Project="first"), _row(Project="shared")])
    second = pd.DataFrame([_row(Project="shared"), _row(Project="last")])

    result = consolidate_dataframes([first, second])

    assert tuple(result.deduplicated_dataframe.columns) == MANDATORY_COLUMNS
    assert result.deduplicated_dataframe["Project"].tolist() == [
        "first",
        "shared",
        "last",
    ]
    assert result.duplicates_detected == result.duplicates_removed == 1
    pd.testing.assert_frame_equal(
        first,
        pd.DataFrame([_row(Project="first"), _row(Project="shared")]),
    )
    pd.testing.assert_frame_equal(
        second,
        pd.DataFrame([_row(Project="shared"), _row(Project="last")]),
    )


def test_empty_input_returns_canonical_empty_dataframe_and_calls_deduplicator_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = consolidation_engine.remove_exact_duplicates
    calls = 0

    def counting_deduplicator(dataframe: pd.DataFrame) -> object:
        nonlocal calls
        calls += 1
        return original(dataframe)

    monkeypatch.setattr(
        consolidation_engine,
        "remove_exact_duplicates",
        counting_deduplicator,
    )

    result = consolidate_dataframes([])

    assert calls == 1
    assert result.deduplicated_dataframe.empty
    assert tuple(result.deduplicated_dataframe.columns) == MANDATORY_COLUMNS
    assert result.duplicates_detected == result.duplicates_removed == 0


def test_duplicate_handler_is_called_once_for_the_whole_batch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = consolidation_engine.remove_exact_duplicates
    calls = 0

    def counting_deduplicator(dataframe: pd.DataFrame) -> object:
        nonlocal calls
        calls += 1
        return original(dataframe)

    monkeypatch.setattr(
        consolidation_engine,
        "remove_exact_duplicates",
        counting_deduplicator,
    )

    consolidate_dataframes(
        [
            pd.DataFrame([_row(Project="A")]),
            pd.DataFrame([_row(Project="A"), _row(Project="B")]),
        ]
    )

    assert calls == 1


def test_rejects_frames_that_are_not_in_the_standard_schema_order() -> None:
    invalid = pd.DataFrame(columns=(*MANDATORY_COLUMNS[1:], MANDATORY_COLUMNS[0]))

    with pytest.raises(ValueError, match="mandatory columns in schema order"):
        consolidate_dataframes([invalid])
