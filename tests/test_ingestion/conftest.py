"""Shared in-memory workbook helpers for ingestion tests."""

from io import BytesIO
from typing import Sequence

from openpyxl import Workbook


class NamedBytesIO(BytesIO):
    """In-memory binary file carrying an uploaded filename."""

    def __init__(self, content: bytes, name: str) -> None:
        super().__init__(content)
        self.name = name


def workbook_bytes(sheets: dict[str, Sequence[Sequence[object]]]) -> bytes:
    """Create an in-memory workbook payload with the requested sheets and rows."""
    workbook = Workbook()
    first_sheet_name = next(iter(sheets))
    worksheet = workbook.active
    worksheet.title = first_sheet_name

    for sheet_name, rows in sheets.items():
        target = (
            worksheet
            if sheet_name == first_sheet_name
            else workbook.create_sheet(sheet_name)
        )
        for row in rows:
            target.append(list(row))

    payload = BytesIO()
    workbook.save(payload)
    return payload.getvalue()
