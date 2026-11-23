"""Tests for RCA data cleaning and standardization."""

from datetime import date, datetime, timezone

import numpy as np
import pandas as pd
import pytest

from config.column_schema import MANDATORY_COLUMNS
from rca_consolidator.processing.data_cleaner import clean_dataframe


def _row(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        column: f"value-{index}" for index, column in enumerate(MANDATORY_COLUMNS)
    }
    values.update(overrides)
    return values


def test_cleaning_preserves_normal_values_and_outputs_schema_order() -> None:
    source = pd.DataFrame(
        [_row(Date=date(2025, 2, 3), Circle="North", **{"Site ID": "00123"})]
    )
    source["Extra"] = "ignore me"

    cleaned = clean_dataframe(source)

    assert tuple(cleaned.columns) == MANDATORY_COLUMNS
    assert len(cleaned) == 1
    assert cleaned.loc[0, "Date"] == "2025-02-03"
    assert cleaned.loc[0, "Circle"] == "North"
    assert cleaned.loc[0, "Site ID"] == "00123"
    assert "Extra" not in cleaned.columns


def test_blank_strings_whitespace_and_nulls_are_normalized_without_dropping_rows() -> None:
    source = pd.DataFrame(
        [
            _row(
                **{
                    "Date": "",
                    "Project": "   ",
                    "Circle": None,
                    "Site ID": np.nan,
                    "Site Name": pd.NA,
                }
            )
        ]
    )

    cleaned = clean_dataframe(source)

    assert len(cleaned) == 1
    for column in ("Date", "Project", "Circle", "Site ID", "Site Name"):
        assert pd.isna(cleaned.loc[0, column])


def test_dates_normalize_only_when_safely_recognized() -> None:
    source = pd.DataFrame(
        [
            _row(Date=datetime(2025, 2, 3, 4, 5, tzinfo=timezone.utc)),
            _row(Date="2025-02-04"),
            _row(Date="2025-02-05T06:07:08"),
            _row(Date="03/04/2025"),
        ]
    )

    cleaned = clean_dataframe(source)

    assert cleaned["Date"].tolist() == [
        "2025-02-03T04:05:00+00:00",
        "2025-02-04",
        "2025-02-05T06:07:08",
        "03/04/2025",
    ]


def test_site_ids_keep_leading_zeros_and_are_not_coerced() -> None:
    source = pd.DataFrame(
        [
            _row(**{"Site ID": "00123"}),
            _row(**{"Site ID": "000045"}),
            _row(**{"Site ID": 123.0}),
            _row(**{"Site ID": None}),
        ]
    )

    cleaned = clean_dataframe(source)

    assert cleaned["Site ID"].tolist()[:2] == ["00123", "000045"]
    assert cleaned.loc[2, "Site ID"] == 123.0
    assert isinstance(cleaned.loc[2, "Site ID"], float)
    assert pd.isna(cleaned.loc[3, "Site ID"])


def test_cleaning_does_not_mutate_original_dataframe() -> None:
    source = pd.DataFrame(
        [_row(Date="2025-02-03", Circle="  North  ", **{"Site ID": "00123"})]
    )
    original = source.copy(deep=True)

    clean_dataframe(source)

    pd.testing.assert_frame_equal(source, original)


def test_missing_mandatory_column_is_not_treated_as_a_blank_cell() -> None:
    source = pd.DataFrame([_row()]).drop(columns=["Circle"])

    with pytest.raises(ValueError, match="missing mandatory columns: Circle"):
        clean_dataframe(source)
