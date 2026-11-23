# Data Dictionary

The future consolidated dataset will retain 12 mandatory standardized columns
from the `RCA_Data` worksheet in source workbooks. Additional columns are
planned to be ignored, while missing mandatory columns will make a workbook
invalid.

Detailed definitions and allowed values for the 12 columns have not yet been
provided. For `Circle`, the value in `RCA_Data` is authoritative: the column is
mandatory, missing columns invalidate the workbook, and blank values must be
flagged in validation results rather than filled. Preserve original Circle
values during consolidation without automatic renaming or correction. Do not
assume a workbook contains only one Circle unless a separate business rule
explicitly establishes that.

This document is reserved for the approved schema; no dataset or sample values
are included in the scaffold.

The standalone cleaning step retains all rows, ignores nonstandard columns,
and returns the 12 mandatory columns in schema order. Empty, whitespace-only,
and null mandatory-cell values are normalized and reported by row and column.
Native dates and unambiguous ISO date values are standardized to ISO 8601;
ambiguous or unsupported date values are preserved and reported. Site ID
values are not coerced, so text identifiers retain their leading zeros. Zeros
represented only by Excel number formatting may not be recoverable through the
current reader.
