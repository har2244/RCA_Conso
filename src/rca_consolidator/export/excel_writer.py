"""Serialize consolidated RCA records into a formatted in-memory workbook."""

from datetime import date, datetime
from io import BytesIO
import math

import pandas as pd

from config.column_schema import MANDATORY_COLUMNS
from rca_consolidator.export.excel_formatter import format_rca_worksheet


def _is_missing(value: object) -> bool:
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def _excel_date_value(value: object) -> object:
    if not isinstance(value, str):
        return value

    text = value.strip()
    try:
        return date.fromisoformat(text)
    except ValueError:
        normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            return value
        return value if parsed.tzinfo is not None else parsed


def _excel_number_value(value: object) -> object:
    if not isinstance(value, str):
        return value
    try:
        numeric_value = float(value.strip())
    except (ValueError, OverflowError):
        return value
    if not math.isfinite(numeric_value):
        return value
    if numeric_value.is_integer():
        return int(numeric_value)
    return numeric_value


def write_rca_workbook(dataframe: pd.DataFrame) -> bytes:
    """Return formatted RCA_Data workbook bytes without changing the input."""
    if tuple(dataframe.columns) != MANDATORY_COLUMNS:
        raise ValueError(
            "Excel export requires exactly the mandatory columns in schema order."
        )

    export_dataframe = dataframe.copy(deep=True)
    export_dataframe["Date"] = [
        _excel_date_value(value) for value in export_dataframe["Date"]
    ]
    export_dataframe["Site ID"] = [
        value if _is_missing(value) else str(value)
        for value in export_dataframe["Site ID"]
    ]
    export_dataframe["Outage Min."] = [
        _excel_number_value(value)
        for value in export_dataframe["Outage Min."]
    ]

    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        export_dataframe.to_excel(
            writer,
            sheet_name="RCA_Data",
            index=False,
        )
        format_rca_worksheet(writer.sheets["RCA_Data"])
    return output.getvalue()