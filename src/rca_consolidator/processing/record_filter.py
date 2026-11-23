"""Filter standardized RCA records for a selected reporting date."""

from dataclasses import dataclass
from datetime import date, datetime
import math

import pandas as pd

from config.column_schema import MANDATORY_COLUMNS
from rca_consolidator.processing.data_cleaner import (
    is_blank_value,
    is_supported_iso_date,
)


@dataclass(frozen=True)
class RecordFilterAudit:
    """Per-file or aggregate record counts and filter-value findings."""

    reporting_date: date
    original_records: int
    records_matching_reporting_date: int
    records_after_om_filter: int
    records_after_outage_filter: int
    excluded_by_reporting_date: int
    excluded_by_om_filter: int
    excluded_by_outage_filter: int
    blank_date_values: int
    invalid_date_values: int
    blank_om_values: int
    invalid_om_values: int
    blank_outage_values: int
    invalid_outage_values: int
    records_after_duplicate_removal: int
    duplicates_removed: int


@dataclass(frozen=True)
class RecordFilterResult:
    """Filtered in-memory records and the corresponding audit counts."""

    dataframe: pd.DataFrame
    audit: RecordFilterAudit


def _calendar_date(value: object) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not isinstance(value, str) or not is_supported_iso_date(value):
        return None

    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return date.fromisoformat(text)
    except ValueError:
        try:
            return datetime.fromisoformat(text).date()
        except ValueError:
            return None


def _positive_number(value: object) -> float | None:
    if is_blank_value(value) or isinstance(value, bool):
        return None
    try:
        numeric_value = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(numeric_value):
        return None
    return numeric_value


def filter_rca_records(
    dataframe: pd.DataFrame,
    reporting_date: date,
) -> RecordFilterResult:
    """Apply date, O&M-start, and positive-outage filters in that order.

    Each filter operates on the output of the prior filter. The input DataFrame
    is never modified, and invalid or blank values are retained in the audit.
    """
    if isinstance(reporting_date, datetime) or not isinstance(reporting_date, date):
        raise ValueError("A reporting date must be selected before consolidation.")
    missing_columns = tuple(
        column for column in MANDATORY_COLUMNS if column not in dataframe.columns
    )
    duplicate_columns = tuple(
        column
        for column in MANDATORY_COLUMNS
        if sum(header == column for header in dataframe.columns) > 1
    )
    if missing_columns or duplicate_columns:
        raise ValueError(
            "Record filtering requires each mandatory RCA column exactly once."
        )

    dates = [_calendar_date(value) for value in dataframe["Date"].tolist()]
    date_matches = [value == reporting_date for value in dates]
    date_filtered = dataframe.loc[date_matches].copy(deep=True)

    om_values = date_filtered["O&M Start (Yes/No)"].tolist()
    om_matches = [
        isinstance(value, str) and value.strip().casefold() == "yes"
        for value in om_values
    ]
    om_filtered = date_filtered.loc[om_matches].copy(deep=True)

    outage_values = om_filtered["Outage Min."].tolist()
    numeric_outages = [_positive_number(value) for value in outage_values]
    outage_matches = [
        value is not None and value > 0 for value in numeric_outages
    ]
    filtered = om_filtered.loc[outage_matches].copy(deep=True)

    original_records = len(dataframe)
    records_matching_reporting_date = len(date_filtered)
    records_after_om_filter = len(om_filtered)
    records_after_outage_filter = len(filtered)
    audit = RecordFilterAudit(
        reporting_date=reporting_date,
        original_records=original_records,
        records_matching_reporting_date=records_matching_reporting_date,
        records_after_om_filter=records_after_om_filter,
        records_after_outage_filter=records_after_outage_filter,
        excluded_by_reporting_date=(
            original_records - records_matching_reporting_date
        ),
        excluded_by_om_filter=(
            records_matching_reporting_date - records_after_om_filter
        ),
        excluded_by_outage_filter=(
            records_after_om_filter - records_after_outage_filter
        ),
        blank_date_values=sum(is_blank_value(value) for value in dataframe["Date"]),
        invalid_date_values=sum(
            not is_blank_value(value) and parsed_date is None
            for value, parsed_date in zip(dataframe["Date"], dates, strict=True)
        ),
        blank_om_values=sum(is_blank_value(value) for value in om_values),
        invalid_om_values=sum(
            not is_blank_value(value)
            and not (
                isinstance(value, str)
                and value.strip().casefold() in ("yes", "no")
            )
            for value in om_values
        ),
        blank_outage_values=sum(is_blank_value(value) for value in outage_values),
        invalid_outage_values=sum(
            not is_blank_value(value) and numeric_value is None
            for value, numeric_value in zip(
                outage_values,
                numeric_outages,
                strict=True,
            )
        ),
        records_after_duplicate_removal=records_after_outage_filter,
        duplicates_removed=0,
    )
    return RecordFilterResult(dataframe=filtered, audit=audit)


def aggregate_filter_audits(
    audits: tuple[RecordFilterAudit, ...],
    reporting_date: date,
) -> RecordFilterAudit:
    """Sum per-file filter counts into a batch audit."""
    count_fields = (
        "original_records",
        "records_matching_reporting_date",
        "records_after_om_filter",
        "records_after_outage_filter",
        "excluded_by_reporting_date",
        "excluded_by_om_filter",
        "excluded_by_outage_filter",
        "blank_date_values",
        "invalid_date_values",
        "blank_om_values",
        "invalid_om_values",
        "blank_outage_values",
        "invalid_outage_values",
        "records_after_duplicate_removal",
        "duplicates_removed",
    )
    if any(audit.reporting_date != reporting_date for audit in audits):
        raise ValueError("All filter audits must use the selected reporting date.")
    totals = {
        field: sum(getattr(audit, field) for audit in audits)
        for field in count_fields
    }
    return RecordFilterAudit(reporting_date=reporting_date, **totals)
