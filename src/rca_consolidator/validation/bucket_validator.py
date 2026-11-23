"""Validate Final Bucket and Bucket - 2 combinations without modifying data."""

from dataclasses import dataclass

import pandas as pd

from rca_consolidator.processing.data_cleaner import is_blank_value


FINAL_BUCKET_TO_SUB_BUCKETS: dict[str, tuple[str, ...]] = {
    "IaasP Power": (
        "Shadow issue",
        "Solar Panel fault",
        "Low solar generation",
        "CCU fault",
        "RM fail",
        "MPPT Issue",
        "Contactor faulty",
        "Power cable faulty",
        "LVD issue",
        "Backplane faulty",
        "SMPS Issue",
        "EB Cable fault",
        "EB tx. Faulty",
        "EB Bill not paid",
        "Meter Faulty",
        "EB Disconnect",
        "EB LT Cable Fault",
        "EB power cut",
        "High V & Low V",
    ),
    "IaasP Others": (
        "IaasP Theft",
        "CT payment Issue",
        "Owner issue",
        "Natural Clamity",
        "Tech Delay",
        "IaasP Link",
    ),
    "IaasP Battery": (
        "Battery issue",
        "BB Theft",
        "Low back Up",
        "BMS faulty",
    ),
    "IaasP OFC": ("Incremental Fiber",),
    "BSNL OFC": (
        "SSA OFC",
        "BSNL OFC",
        "ETR OFC",
        "BBNL OFC",
        "WTR OFC",
        "NTR",
        "CNTX",
        "JCNL",
        "Maha IT",
        "Pace OFC",
    ),
    "BSNL Media": (
        "Nokia mini link",
        "NEC Mini link",
        "CPAN issue",
        "Maan Media issue",
        "BSNL Link",
        "Vsat Media",
        "BSNL Hub",
        "BSNL Others",
        "Fluctuation",
    ),
    "Others": (
        "4G Sat. link site",
        "IP site link",
        "Others site link",
        "ATC site link",
        "Non IaasP Theft",
        "Fire Incident",
    ),
    "TCS": (
        "RAC Card",
        "CEF Card",
        "CEF12 Card",
        "FTU",
        "RRH Hardware",
        "RRH Cable",
        "RRH Cipri Cable",
        "BBU",
        "Partial band",
        "S1 Link",
        "Fluctuation",
    ),
    "DMW": (
        "Ceragoan Radio",
        "DMW Cipri Cable",
        "DMW Power cable",
        "DMW RSL Issue",
        "DMW pole mount Issue",
        "Fluctuation",
        "Cascading Cable",
    ),
    "HFCL": (
        "HFCL Radio",
        "HFCL Switch",
        "HFCL POE",
        "HFCL Power cable",
        "HFCL RSL Issue",
        "HFCL Pole mount Issue",
        "HFCL Port",
        "HFCL MCX0",
        "Fluctuation",
    ),
}


@dataclass(frozen=True)
class BucketValidationIssue:
    """Bucket finding with source workbook and worksheet row provenance."""

    source_filename: str
    excel_row_number: int
    final_bucket: object
    bucket_2: object
    reason: str


@dataclass(frozen=True)
class BucketValidationResult:
    """Valid and invalid record counts plus individual bucket findings."""

    valid_records: int
    invalid_records: int
    issues: tuple[BucketValidationIssue, ...]


def _comparison_value(value: object) -> str | None:
    if not isinstance(value, str) or is_blank_value(value):
        return None
    return value.strip().casefold()


_NORMALIZED_BUCKETS = {
    _comparison_value(final_bucket): final_bucket
    for final_bucket in FINAL_BUCKET_TO_SUB_BUCKETS
}
_NORMALIZED_SUB_BUCKETS = {
    final_bucket: {
        _comparison_value(sub_bucket): sub_bucket
        for sub_bucket in sub_buckets
    }
    for final_bucket, sub_buckets in FINAL_BUCKET_TO_SUB_BUCKETS.items()
}


def validate_bucket_combinations(
    dataframe: pd.DataFrame,
    *,
    source_filename: str,
    header_row: int = 1,
) -> BucketValidationResult:
    """Validate every row's bucket pair and report Excel row numbers.

    Values are compared case-insensitively after trimming outer whitespace.
    The input values and DataFrame are never changed.
    """
    if header_row < 1:
        raise ValueError("header_row must be a positive one-based row number.")
    if any(
        sum(column == name for column in dataframe.columns) > 1
        for name in ("Final Bucket", "Bucket - 2")
    ):
        raise ValueError("Bucket validation requires unique bucket columns.")

    final_values = (
        dataframe["Final Bucket"].tolist()
        if "Final Bucket" in dataframe.columns
        else [None] * len(dataframe)
    )
    sub_values = (
        dataframe["Bucket - 2"].tolist()
        if "Bucket - 2" in dataframe.columns
        else [None] * len(dataframe)
    )

    issues: list[BucketValidationIssue] = []
    invalid_row_positions: set[int] = set()
    for row_position, (final_value, sub_value) in enumerate(
        zip(final_values, sub_values, strict=True)
    ):
        row_issues: list[str] = []
        normalized_final = _comparison_value(final_value)
        normalized_sub = _comparison_value(sub_value)

        if is_blank_value(final_value):
            row_issues.append("Missing Final Bucket.")
        elif normalized_final not in _NORMALIZED_BUCKETS:
            row_issues.append(f"Invalid Final Bucket value: {final_value!r}.")

        if is_blank_value(sub_value):
            row_issues.append("Missing Bucket - 2.")
        elif normalized_final in _NORMALIZED_BUCKETS:
            canonical_final = _NORMALIZED_BUCKETS[normalized_final]
            if normalized_sub not in _NORMALIZED_SUB_BUCKETS[canonical_final]:
                row_issues.append(
                    f"Bucket - 2 value {sub_value!r} is not allowed for "
                    f"Final Bucket {final_value!r}."
                )
        elif not is_blank_value(final_value):
            row_issues.append(
                "Bucket - 2 cannot be validated because Final Bucket is invalid."
            )

        if row_issues:
            invalid_row_positions.add(row_position)
            excel_row_number = header_row + row_position + 1
            issues.extend(
                BucketValidationIssue(
                    source_filename=source_filename,
                    excel_row_number=excel_row_number,
                    final_bucket=final_value,
                    bucket_2=sub_value,
                    reason=reason,
                )
                for reason in row_issues
            )

    invalid_records = len(invalid_row_positions)
    return BucketValidationResult(
        valid_records=len(dataframe) - invalid_records,
        invalid_records=invalid_records,
        issues=tuple(issues),
    )
