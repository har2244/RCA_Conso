"""Canonical RCA worksheet columns and column-mapping thresholds."""

MANDATORY_COLUMNS = (
    "Date",
    "Project",
    "Circle",
    "Site ID",
    "Site Name",
    "OA",
    "BA",
    "O&M Start (Yes/No)",
    "Outage Min.",
    "Final Bucket",
    "Bucket - 2",
    "RCA",
)

FUZZY_MATCH_THRESHOLD = 85.0
FUZZY_AMBIGUITY_MARGIN = 5.0