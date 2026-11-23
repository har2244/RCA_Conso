"""Clean RCA records without changing the source DataFrame."""

import re
from datetime import date, datetime

import pandas as pd

from config.column_schema import MANDATORY_COLUMNS


_ISO_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_ISO_DATETIME_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}[Tt ]\d{2}:\d{2}"
    r"(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:\d{2})?$"
)


def is_blank_value(value: object) -> bool:
    """Return whether a scalar is null, an empty string, or whitespace-only."""
    if isinstance(value, str):
        return not value.strip()
    if pd.api.types.is_scalar(value):
        return bool(pd.isna(value))
    return False


def _parse_iso_date(value: object) -> str | None:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if not isinstance(value, str):
        return None

    text = value.strip()
    if _ISO_DATE_PATTERN.fullmatch(text):
        try:
            return date.fromisoformat(text).isoformat()
        except ValueError:
            return None
    if not _ISO_DATETIME_PATTERN.fullmatch(text):
        return None

    iso_text = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        return datetime.fromisoformat(iso_text).isoformat()
    except ValueError:
        return None


def is_supported_iso_date(value: object) -> bool:
    """Return whether a value is a native date or an unambiguous ISO date."""
    return _parse_iso_date(value) is not None


def _standardize_date(value: object) -> object:
    standardized = _parse_iso_date(value)
    return value if standardized is None else standardized


def clean_dataframe(dataframe: pd.DataFrame) -> pd.DataFrame:
    """Return standardized RCA columns in schema order, retaining every row.

    The input must already have canonical mandatory headers. Header mapping and
    missing-column schema validation remain the responsibility of their
    existing modules.
    """
    missing_columns = tuple(
        column for column in MANDATORY_COLUMNS if column not in dataframe.columns
    )
    duplicate_columns = tuple(
        column
        for column in MANDATORY_COLUMNS
        if sum(header == column for header in dataframe.columns) > 1
    )
    if missing_columns:
        raise ValueError(
            "Cannot clean a DataFrame with missing mandatory columns: "
            + ", ".join(missing_columns)
        )
    if duplicate_columns:
        raise ValueError(
            "Cannot clean a DataFrame with duplicate mandatory columns: "
            + ", ".join(duplicate_columns)
        )

    cleaned = dataframe.loc[:, list(MANDATORY_COLUMNS)].copy(deep=True)
    for column in MANDATORY_COLUMNS:
        values = cleaned[column].tolist()
        normalized_values = [
            pd.NA if is_blank_value(value) else value for value in values
        ]
        if any(is_blank_value(value) for value in values):
            cleaned[column] = normalized_values

    cleaned["Date"] = [
        _standardize_date(value) for value in cleaned["Date"].tolist()
    ]
    return cleaned