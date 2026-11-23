"""Tests for Final Bucket and Bucket - 2 combinations."""

import pandas as pd

from rca_consolidator.validation.bucket_validator import (
    validate_bucket_combinations,
)


def test_accepts_case_and_outer_space_variations_without_changing_values() -> None:
    dataframe = pd.DataFrame(
        {
            "Final Bucket": ["  iaasp POWER "],
            "Bucket - 2": [" Shadow ISSUE  "],
        }
    )
    original = dataframe.copy(deep=True)

    result = validate_bucket_combinations(
        dataframe,
        source_filename="power.xlsx",
        header_row=3,
    )

    assert result.valid_records == 1
    assert result.invalid_records == 0
    assert result.issues == ()
    pd.testing.assert_frame_equal(dataframe, original)


def test_flags_invalid_bucket_combinations_and_missing_values_separately() -> None:
    dataframe = pd.DataFrame(
        {
            "Final Bucket": [
                "IaasP Power",
                "Unknown",
                None,
                "BSNL Media",
            ],
            "Bucket - 2": [
                "Nokia mini link",
                "Nokia mini link",
                None,
                " ",
            ],
        }
    )

    result = validate_bucket_combinations(
        dataframe,
        source_filename="invalid.xlsx",
        header_row=2,
    )

    assert result.valid_records == 0
    assert result.invalid_records == 4
    assert {
        (issue.excel_row_number, issue.reason)
        for issue in result.issues
    } == {
        (3, "Bucket - 2 value 'Nokia mini link' is not allowed for Final Bucket 'IaasP Power'."),
        (4, "Invalid Final Bucket value: 'Unknown'."),
        (4, "Bucket - 2 cannot be validated because Final Bucket is invalid."),
        (5, "Missing Final Bucket."),
        (5, "Missing Bucket - 2."),
        (6, "Missing Bucket - 2."),
    }
    assert all(issue.source_filename == "invalid.xlsx" for issue in result.issues)


def test_fluctuation_is_valid_only_for_its_four_final_buckets() -> None:
    dataframe = pd.DataFrame(
        {
            "Final Bucket": [
                "BSNL Media",
                "TCS",
                "DMW",
                "HFCL",
                "Others",
            ],
            "Bucket - 2": ["Fluctuation"] * 5,
        }
    )

    result = validate_bucket_combinations(
        dataframe,
        source_filename="fluctuation.xlsx",
    )

    assert result.valid_records == 4
    assert result.invalid_records == 1
    assert len(result.issues) == 1
    assert result.issues[0].excel_row_number == 6
    assert "not allowed for Final Bucket 'Others'" in result.issues[0].reason


def test_missing_bucket_column_is_reported_for_each_record() -> None:
    dataframe = pd.DataFrame({"Final Bucket": ["TCS", "HFCL"]})

    result = validate_bucket_combinations(
        dataframe,
        source_filename="missing-column.xlsx",
    )

    assert result.valid_records == 0
    assert result.invalid_records == 2
    assert [issue.reason for issue in result.issues] == [
        "Missing Bucket - 2.",
        "Missing Bucket - 2.",
    ]
