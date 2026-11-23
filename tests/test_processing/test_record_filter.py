"""Tests for reporting-date, O&M, and outage record filtering."""

from datetime import date, datetime

import pandas as pd
import pytest

from config.column_schema import MANDATORY_COLUMNS
from rca_consolidator.processing.record_filter import filter_rca_records


def _row(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        column: f"value-{index}" for index, column in enumerate(MANDATORY_COLUMNS)
    }
    values.update(
        {
            "Date": date(2025, 4, 15),
            "O&M Start (Yes/No)": "Yes",
            "Outage Min.": 5,
        }
    )
    values.update(overrides)
    return values


def test_filters_in_order_and_reports_stage_counts_without_changing_input() -> None:
    dataframe = pd.DataFrame(
        [
            _row(
                Date=datetime(2025, 4, 15, 23, 45),
                **{"O&M Start (Yes/No)": " yEs ", "Site ID": "one"},
            ),
            _row(**{"O&M Start (Yes/No)": " No "}),
            _row(**{"Outage Min.": 0}),
            _row(**{"Outage Min.": -1}),
            _row(**{"Outage Min.": None}),
            _row(**{"Outage Min.": "unknown"}),
            _row(
                Date="2025-04-15T00:15:00",
                **{"Outage Min.": "2.5", "Site ID": "two"},
            ),
            _row(Date=date(2025, 4, 16)),
            _row(Date=None),
            _row(Date="not-a-date"),
            _row(**{"O&M Start (Yes/No)": "Maybe"}),
            _row(**{"O&M Start (Yes/No)": "  "}),
        ],
        columns=MANDATORY_COLUMNS,
    )
    original = dataframe.copy(deep=True)

    result = filter_rca_records(dataframe, date(2025, 4, 15))

    assert result.dataframe["Site ID"].tolist() == ["one", "two"]
    assert result.dataframe.index.tolist() == [0, 6]
    assert dataframe.equals(original)
    assert result.audit.original_records == 12
    assert result.audit.records_matching_reporting_date == 9
    assert result.audit.records_after_om_filter == 6
    assert result.audit.records_after_outage_filter == 2
    assert result.audit.excluded_by_reporting_date == 3
    assert result.audit.excluded_by_om_filter == 3
    assert result.audit.excluded_by_outage_filter == 4
    assert result.audit.blank_date_values == 1
    assert result.audit.invalid_date_values == 1
    assert result.audit.blank_om_values == 1
    assert result.audit.invalid_om_values == 1
    assert result.audit.blank_outage_values == 1
    assert result.audit.invalid_outage_values == 1
    assert (
        result.audit.original_records
        == result.audit.excluded_by_reporting_date
        + result.audit.excluded_by_om_filter
        + result.audit.excluded_by_outage_filter
        + result.audit.records_after_outage_filter
    )


def test_empty_result_keeps_standard_schema() -> None:
    dataframe = pd.DataFrame([_row(Date=date(2025, 4, 16))])

    result = filter_rca_records(dataframe, date(2025, 4, 15))

    assert result.dataframe.empty
    assert tuple(result.dataframe.columns) == MANDATORY_COLUMNS
    assert result.audit.records_after_outage_filter == 0


@pytest.mark.parametrize("reporting_date", [None, datetime(2025, 4, 15)])
def test_filter_requires_a_calendar_date(reporting_date: object) -> None:
    dataframe = pd.DataFrame([_row()])

    with pytest.raises(ValueError, match="reporting date"):
        filter_rca_records(dataframe, reporting_date)  # type: ignore[arg-type]
