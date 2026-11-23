"""Validation helpers for uploaded Excel files."""

from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Iterable


SUPPORTED_EXTENSIONS = {".xlsx", ".xlsm"}


@dataclass(frozen=True)
class FileValidationResult:
    """Validation outcome for one uploaded file."""

    filename: str
    file: BinaryIO
    error: str | None = None

    @property
    def is_valid(self) -> bool:
        """Return whether the uploaded file passed basic validation."""
        return self.error is None


def validate_uploaded_file(
    uploaded_file: BinaryIO,
    filename: str | None = None,
) -> FileValidationResult:
    """Validate one uploaded file without writing to disk or changing its cursor."""
    original_name = filename if filename is not None else getattr(uploaded_file, "name", None)
    if not isinstance(original_name, str) or not original_name.strip():
        return FileValidationResult(
            filename="<unnamed>",
            file=uploaded_file,
            error="The uploaded file has no usable filename.",
        )

    if Path(original_name).suffix.lower() not in SUPPORTED_EXTENSIONS:
        return FileValidationResult(
            filename=original_name,
            file=uploaded_file,
            error="Unsupported file extension; expected .xlsx or .xlsm.",
        )

    original_position: int | None = None
    error: str | None = None
    try:
        original_position = uploaded_file.tell()
        uploaded_file.seek(0)
        first_byte = uploaded_file.read(1)
        if not isinstance(first_byte, (bytes, bytearray)):
            error = "The uploaded file is not a readable binary stream."
        elif not first_byte:
            error = "The uploaded file is empty."
    except (AttributeError, OSError, TypeError, ValueError) as exc:
        error = f"The uploaded file could not be read: {exc}"
    finally:
        if original_position is not None:
            try:
                uploaded_file.seek(original_position)
            except (AttributeError, OSError, TypeError, ValueError) as exc:
                error = f"The uploaded file position could not be restored: {exc}"

    return FileValidationResult(
        filename=original_name,
        file=uploaded_file,
        error=error,
    )


def validate_uploaded_files(
    uploaded_files: Iterable[BinaryIO],
) -> list[FileValidationResult]:
    """Validate each uploaded file independently and retain individual errors."""
    return [validate_uploaded_file(uploaded_file) for uploaded_file in uploaded_files]