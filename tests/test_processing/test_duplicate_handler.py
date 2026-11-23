"""Tests for exact duplicate removal across standardized RCA records."""

import numpy as np
import pandas as pd
import pytest

from config.column_schema import MANDATORY_COLUMNS
from rca_consolidator.processing.duplicate_handler import remove_exact_duplicates


def _row(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        column: f"value-{index}" for index, column in enumerate(MANDATORY_COLUMNS)
    }
    values.update(overrides)
    return values


def test_no_duplicates_returns_all_rows_and_zero_counts() -> None:
    source = pd.DataFrame([_row(Project="A"), _row(Project="B")])

    result = remove_exact_duplicates(source)

    pd.testing.assert_frame_equal(result.deduplicated_dataframe, source)
    assert result.duplicates_detected == 0
    assert result.duplicates_removed == 0


def test_exact_duplicates_within_one_file_keep_first_occurrence() -> None:
    source = pd.DataFrame(
        [_row(Project="A"), _row(Project="B"), _row(Project="A")],
        index=["first-A", "B", "second-A"],
    )

    result = remove_exact_duplicates(source)

    assert result.deduplicated_dataframe.index.tolist() == ["first-A", "B"]
    assert result.duplicates_detected == 1
    assert result.duplicates_removed == 1


def test_duplicates_across_concatenated_files_are_removed_together() -> None:
    first_file = pd.DataFrame([_row(Project="A"), _row(Project="B")])
    second_file = pd.DataFrame([_row(Project="B"), _row(Project="C")])
    combined = pd.concat([first_file, second_file], ignore_index=True)

    result = remove_exact_duplicates(combined)

    assert result.deduplicated_dataframe["Project"].tolist() == ["A", "B", "C"]
    assert result.duplicates_detected == 1
    assert result.duplicates_removed == 1


def test_first_occurrence_and_original_row_order_are_preserved() -> None:
    source = pd.DataFrame(
        [
            _row(Project="A", RCA="first"),
            _row(Project="B", RCA="middle"),
            _row(Project="A", RCA="first"),
            _row(Project="C", RCA="last"),
        ],
        index=[9, 3, 7, 1],
    )

    result = remove_exact_duplicates(source)

    assert result.deduplicated_dataframe.index.tolist() == [9, 3, 1]
    assert result.deduplicated_dataframe["Project"].tolist() == ["A", "B", "C"]


def test_same_site_id_with_different_rca_values_are_retained() -> None:
    source = pd.DataFrame(
        [
            _row(**{"Site ID": "00123", "RCA": "Power"}),
            _row(**{"Site ID": "00123", "RCA": "Transmission"}),
        ]
    )

    result = remove_exact_duplicates(source)

    assert len(result.deduplicated_dataframe) == 2
    assert result.duplicates_removed == 0


def test_same_record_with_different_circles_is_retained() -> None:
    source = pd.DataFrame(
        [
            _row(Circle="North"),
            _row(Circle="South"),
        ]
    )

    result = remove_exact_duplicates(source)

    assert len(result.deduplicated_dataframe) == 2
    assert result.duplicates_removed == 0


def test_missing_values_are_compared_consistently() -> None:
    first = _row(Project="A", **{"Site Name": pd.NA})
    second = _row(Project="A", **{"Site Name": None})
    third = _row(Project="A", **{"Site Name": np.nan})
    source = pd.DataFrame([first, second, third], dtype=object)

    result = remove_exact_duplicates(source)

    assert len(result.deduplicated_dataframe) == 1
    assert pd.isna(result.deduplicated_dataframe.iloc[0]["Site Name"])
    assert result.duplicates_removed == 2


def test_numeric_integer_and_float_values_follow_pandas_equality() -> None:
    source = pd.DataFrame(
        [
            _row(**{"Site ID": 123}),
            _row(**{"Site ID": 123.0}),
        ],
        dtype=object,
    )

    result = remove_exact_duplicates(source)

    assert len(result.deduplicated_dataframe) == 1
    assert result.duplicates_removed == 1


def test_text_numeric_string_remains_distinct_from_numeric_value() -> None:
    source = pd.DataFrame(
        [
            _row(**{"Site ID": "123"}),
            _row(**{"Site ID": 123}),
        ],
        dtype=object,
    )

    result = remove_exact_duplicates(source)

    assert len(result.deduplicated_dataframe) == 2
    assert result.duplicates_removed == 0


@pytest.mark.parametrize(
    "columns",
    [
        tuple(column for column in MANDATORY_COLUMNS if column != "RCA"),
        (*MANDATORY_COLUMNS, "Extra"),
        (*MANDATORY_COLUMNS[1:], MANDATORY_COLUMNS[0]),
        (*MANDATORY_COLUMNS, "Project"),
    ],
)
def test_invalid_or_missing_columns_are_rejected(
    columns: tuple[str, ...],
) -> None:
    source = pd.DataFrame(columns=columns)

    with pytest.raises(ValueError, match="exactly the mandatory columns"):
        remove_exact_duplicates(source)


def test_input_dataframe_is_unchanged_and_result_is_a_copy() -> None:
    source = pd.DataFrame([_row(Project="A"), _row(Project="A")])
    original = source.copy(deep=True)

    result = remove_exact_duplicates(source)
    result.deduplicated_dataframe.loc[0, "Project"] = "changed"

    pd.testing.assert_frame_equal(source, original)
    assert result.deduplicated_dataframe is not source
