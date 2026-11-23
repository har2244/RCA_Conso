"""Read source data from the required worksheet in uploaded Excel workbooks."""

import math
import re
from dataclasses import dataclass
from typing import BinaryIO, Sequence
from xml.etree.ElementTree import ParseError
from zipfile import BadZipFile

import pandas as pd
from openpyxl.utils.exceptions import InvalidFileException

from rca_consolidator.ingestion.header_detector import (
    HeaderDetectionStatus,
    detect_header_row,
)
from rca_consolidator.ingestion.sheet_detector import RCA_DATA_SHEET


SITE_ID_FORMAT_FINDINGS_ATTR = "rca_site_id_format_findings"
HEADER_ROW_ATTR = "rca_header_row"
_ZERO_PLACEHOLDER_FORMAT = re.compile(r"^0+$")


@dataclass(frozen=True)
class SiteIdFormatFinding:
    """Unsupported Site ID number formatting that was preserved without guessing."""

    workbook_name: str
    row_position: int
    dataframe_index: object
    excel_row: int
    source_column_position: int
    cell_coordinate: str
    raw_value: object
    number_format: str
    reason: str


class ExcelReadError(Exception):
    """Raised when an uploaded workbook cannot be read as an Excel file."""


class WorksheetNotFoundError(ExcelReadError):
    """Raised when the required worksheet is absent from a workbook."""


class EmptyWorksheetError(ExcelReadError):
    """Raised when the required worksheet contains no cells or headers."""


class HeaderNotDetectedError(ExcelReadError):
    """Raised when no reliable RCA header is found in the first five rows."""

    def __init__(self) -> None:
        super().__init__("Header not detected within the first 5 rows.")


class AmbiguousHeaderRowError(ExcelReadError):
    """Raised when multiple first-five rows are equally plausible headers."""

    def __init__(self, candidate_rows: Sequence[int]) -> None:
        self.candidate_rows = tuple(candidate_rows)
        candidates = ", ".join(str(row) for row in self.candidate_rows)
        super().__init__(
            "Header detection is ambiguous; candidate Excel rows: "
            f"{candidates}. Manual review is required."
        )


def _preserve_as_text(value: object) -> object:
    """Keep configured text-column values textual while preserving blank cells."""
    return value if value is None else str(value)


def _zero_pad_site_id(value: object, number_format: str) -> str | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        integer_value = value
    elif isinstance(value, float) and math.isfinite(value) and value.is_integer():
        integer_value = int(value)
    else:
        return None
    if integer_value < 0:
        return None
    return f"{integer_value:0{len(number_format)}d}"


def read_rca_data(
    uploaded_file: BinaryIO,
    *,
    header_row: int | None = 1,
    text_columns: Sequence[str] = (),
    filename: str | None = None,
) -> pd.DataFrame:
    """Read only `RCA_Data`, preserving source headers and optionally text IDs.

    Passing `header_row=None` scans the first five worksheet rows for the RCA
    schema. An explicit one-based row remains available for manual resolution.
    `text_columns` preserves selected values as text where possible.
    Site IDs are processed per cell so supported Excel zero formats are retained.
    """
    if header_row is not None and header_row < 1:
        raise ValueError("header_row must be a positive, one-based row number.")

    original_name = filename
    if original_name is None:
        candidate_name = getattr(uploaded_file, "name", None)
        original_name = (
            candidate_name
            if isinstance(candidate_name, str) and candidate_name
            else "<uploaded file>"
        )

    original_position: int | None = None
    data: pd.DataFrame | None = None
    error: ExcelReadError | None = None
    site_id_findings: list[SiteIdFormatFinding] = []

    try:
        original_position = uploaded_file.tell()
        uploaded_file.seek(0)
        with pd.ExcelFile(uploaded_file, engine="openpyxl") as workbook:
            if RCA_DATA_SHEET not in workbook.sheet_names:
                raise WorksheetNotFoundError(
                    f"Worksheet '{RCA_DATA_SHEET}' was not found in '{original_name}'."
                )
            selected_header_row = header_row
            if selected_header_row is None:
                header_preview = workbook.parse(
                    sheet_name=RCA_DATA_SHEET,
                    header=None,
                    nrows=5,
                    dtype=object,
                    keep_default_na=False,
                )
                detection = detect_header_row(header_preview)
                if detection.status is HeaderDetectionStatus.NOT_FOUND:
                    raise HeaderNotDetectedError()
                if detection.status is HeaderDetectionStatus.AMBIGUOUS:
                    raise AmbiguousHeaderRowError(detection.candidate_rows)
                selected_header_row = detection.header_row
            if selected_header_row is None:
                raise HeaderNotDetectedError()
            data = workbook.parse(
                sheet_name=RCA_DATA_SHEET,
                header=selected_header_row - 1,
                dtype=object,
                keep_default_na=False,
            )
            site_id_column_positions: list[int] = []
            if "Site ID" in data.columns:
                worksheet = workbook.book[RCA_DATA_SHEET]
                site_id_column_positions = [
                    column_position
                    for column_position in range(len(data.columns))
                    if worksheet.cell(
                        row=selected_header_row,
                        column=column_position + 1,
                    ).value
                    == "Site ID"
                ]

                for column_position in site_id_column_positions:
                    if not len(data):
                        continue
                    rows = worksheet.iter_rows(
                        min_row=selected_header_row + 1,
                        max_row=selected_header_row + len(data),
                        min_col=column_position + 1,
                        max_col=column_position + 1,
                    )
                    for row_position, (cell,) in enumerate(rows):
                        value = cell.value
                        if value is None or (isinstance(value, str) and value == ""):
                            continue
                        if isinstance(value, str):
                            continue

                        number_format = getattr(cell, "number_format", "General")
                        if number_format.casefold() == "general":
                            continue
                        if _ZERO_PLACEHOLDER_FORMAT.fullmatch(number_format):
                            formatted_value = _zero_pad_site_id(value, number_format)
                            if formatted_value is not None:
                                data.iat[row_position, column_position] = formatted_value
                                continue
                            reason = (
                                "A zero-placeholder format requires a "
                                "nonnegative integral value."
                            )
                        else:
                            reason = "The Site ID number format is unsupported."
                        site_id_findings.append(
                            SiteIdFormatFinding(
                                workbook_name=original_name,
                                row_position=row_position,
                                dataframe_index=data.index[row_position],
                                excel_row=selected_header_row + row_position + 1,
                                source_column_position=column_position + 1,
                                cell_coordinate=cell.coordinate,
                                raw_value=data.iat[row_position, column_position],
                                number_format=number_format,
                                reason=reason,
                            )
                        )

            for column in text_columns:
                if column in data.columns:
                    if column == "Site ID":
                        finding_positions = {
                            (finding.row_position, finding.source_column_position - 1)
                            for finding in site_id_findings
                        }
                        for column_position in site_id_column_positions:
                            for row_position in range(len(data)):
                                if (row_position, column_position) not in finding_positions:
                                    data.iat[row_position, column_position] = (
                                        _preserve_as_text(
                                            data.iat[row_position, column_position]
                                        )
                                    )
                    else:
                        data[column] = data[column].map(_preserve_as_text)
            data.attrs[SITE_ID_FORMAT_FINDINGS_ATTR] = tuple(site_id_findings)
            data.attrs[HEADER_ROW_ATTR] = selected_header_row
    except WorksheetNotFoundError as exc:
        error = exc
    except (
        AttributeError,
        BadZipFile,
        EOFError,
        IndexError,
        InvalidFileException,
        KeyError,
        OSError,
        ParseError,
        TypeError,
        ValueError,
    ) as exc:
        error = ExcelReadError(
            f"Could not read worksheet '{RCA_DATA_SHEET}' from "
            f"'{original_name}': {exc}"
        )
        error.__cause__ = exc
    finally:
        if original_position is not None:
            try:
                uploaded_file.seek(original_position)
            except (AttributeError, OSError, TypeError, ValueError) as exc:
                error = ExcelReadError(
                    f"Could not restore uploaded file position for "
                    f"'{original_name}': {exc}"
                )

    if error is not None:
        raise error
    if data is None:
        raise ExcelReadError(f"No data was read from '{original_name}'.")
    if data.shape == (0, 0):
        raise EmptyWorksheetError(
            f"Worksheet '{RCA_DATA_SHEET}' in '{original_name}' is empty."
        )
    return data