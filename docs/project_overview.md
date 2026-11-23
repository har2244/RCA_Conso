# Project Overview

RCA Consolidation System consolidates daily telecom Root Cause Analysis data
from Excel workbooks received from multiple circles.

The implemented workflow reads the `RCA_Data` worksheet, retains 12 mandatory
columns, rejects missing schema, presents mapping corrections for approval,
uses worksheet `Circle` values, validates Project and bucket findings, applies
the reporting-date/O&M/outage filters, removes exact duplicates, and exports a
formatted `RCA_Data` workbook.

Circle-wise/overall summary sheets and standalone validation workbook export
remain unimplemented.
