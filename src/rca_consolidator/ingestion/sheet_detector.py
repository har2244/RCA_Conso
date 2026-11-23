"""Identify the required worksheet in an uploaded Excel workbook."""

from dataclasses import dataclass
from typing import BinaryIO
from xml.etree.ElementTree import ParseError
from zipfile import BadZipFile

import pandas as pd
from openpyxl.utils.exceptions import InvalidFileException


RCA_DATA_SHEET = "RCA_Data"


@dataclass(frozen=True)
class SheetDetectionResult:
    """Outcome of checking a workbook for the required worksheet."""

    filename: str
    found: bool
    sheet_name: str | None = None
    error: str | None = None


def detect_rca_data_sheet(
    uploaded_file: BinaryIO,
    filename: str | None = None,
) -> SheetDetectionResult:
    """Find the exact `RCA_Data` worksheet without parsing worksheet contents."""
    original_name = filename
    if original_name is None:
        candidate_name = getattr(uploaded_file, "name", None)
        original_name = (
            candidate_name
            if isinstance(candidate_name, str) and candidate_name
            else "<uploaded file>"
        )

    original_position: int | None = None
    result: SheetDetectionResult | None = None
    try:
        original_position = uploaded_file.tell()
        uploaded_file.seek(0)
        with pd.ExcelFile(uploaded_file, engine="openpyxl") as workbook:
            if RCA_DATA_SHEET in workbook.sheet_names:
                result = SheetDetectionResult(
                    filename=original_name,
                    found=True,
                    sheet_name=RCA_DATA_SHEET,
                )
            else:
                result = SheetDetectionResult(
                    filename=original_name,
                    found=False,
                    error=f"Worksheet '{RCA_DATA_SHEET}' was not found.",
                )
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
        result = SheetDetectionResult(
            filename=original_name,
            found=False,
            error=f"Could not inspect workbook: {exc}",
        )
    finally:
        if original_position is not None:
            try:
                uploaded_file.seek(original_position)
            except (AttributeError, OSError, TypeError, ValueError) as exc:
                result = SheetDetectionResult(
                    filename=original_name,
                    found=False,
                    error=f"Could not restore uploaded file position: {exc}",
                )

    if result is None:
        return SheetDetectionResult(
            filename=original_name,
            found=False,
            error="Could not inspect workbook.",
        )
    return result