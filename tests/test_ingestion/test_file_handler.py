"""Tests for uploaded file validation."""

from io import BytesIO

from rca_consolidator.ingestion.file_handler import (
    validate_uploaded_file,
    validate_uploaded_files,
)
from tests.test_ingestion.conftest import NamedBytesIO, workbook_bytes


def test_accepts_xlsx_and_xlsm_files() -> None:
    content = workbook_bytes({"RCA_Data": [["Site ID"]]})

    for filename in ("source.xlsx", "source.xlsm"):
        uploaded_file = NamedBytesIO(content, filename)
        result = validate_uploaded_file(uploaded_file)

        assert result.is_valid
        assert result.filename == filename
        assert result.file is uploaded_file


def test_rejects_unsupported_extension() -> None:
    result = validate_uploaded_file(NamedBytesIO(b"data", "source.csv"))

    assert not result.is_valid
    assert "Unsupported file extension" in result.error


def test_rejects_empty_file_and_preserves_cursor() -> None:
    uploaded_file = NamedBytesIO(b"", "empty.xlsx")
    result = validate_uploaded_file(uploaded_file)

    assert not result.is_valid
    assert result.error == "The uploaded file is empty."
    assert uploaded_file.tell() == 0


def test_preserves_cursor_for_valid_file() -> None:
    uploaded_file = NamedBytesIO(b"workbook-content", "source.xlsx")
    uploaded_file.seek(4)

    result = validate_uploaded_file(uploaded_file)

    assert result.is_valid
    assert uploaded_file.tell() == 4


def test_handles_unreadable_file() -> None:
    class UnreadableFile(BytesIO):
        def read(self, size: int = -1) -> bytes:
            raise OSError("read failed")

    uploaded_file = UnreadableFile(b"payload")
    uploaded_file.name = "unreadable.xlsx"
    result = validate_uploaded_file(uploaded_file)

    assert not result.is_valid
    assert "could not be read" in result.error


def test_batch_validation_keeps_individual_file_errors() -> None:
    valid = NamedBytesIO(workbook_bytes({"RCA_Data": [["Site ID"]]}), "valid.xlsx")
    invalid = NamedBytesIO(b"not a workbook", "invalid.csv")

    results = validate_uploaded_files([valid, invalid])

    assert len(results) == 2
    assert results[0].is_valid
    assert results[0].filename == "valid.xlsx"
    assert not results[1].is_valid
    assert results[1].filename == "invalid.csv"


def test_rejects_files_without_a_filename() -> None:
    result = validate_uploaded_file(BytesIO(b"content"))

    assert not result.is_valid
    assert result.filename == "<unnamed>"
    assert "no usable filename" in result.error
