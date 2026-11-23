"""Detect an RCA header row using the existing column-mapping rules."""

from dataclasses import dataclass
from enum import Enum

import pandas as pd

from config.column_schema import MANDATORY_COLUMNS
from rca_consolidator.processing.column_mapper import (
    MappingStatus,
    map_columns,
)


HEADER_SCAN_ROWS = 5
MINIMUM_HEADER_MATCHES = (len(MANDATORY_COLUMNS) + 1) // 2


class HeaderDetectionStatus(str, Enum):
    """Outcome of scanning the first worksheet rows for a schema header."""

    DETECTED = "DETECTED"
    NOT_FOUND = "NOT_FOUND"
    AMBIGUOUS = "AMBIGUOUS"


@dataclass(frozen=True)
class HeaderRowCandidate:
    """Header-row match score used to rank candidate Excel rows."""

    excel_row: int
    matched_columns: tuple[str, ...]
    exact_match_count: int
    similarity_score: float

    @property
    def rank(self) -> tuple[int, int, float]:
        """Rank coverage first, then unambiguous and fuzzy match strength."""
        return (
            len(self.matched_columns),
            self.exact_match_count,
            self.similarity_score,
        )


@dataclass(frozen=True)
class HeaderDetectionResult:
    """Detected row or candidate rows requiring manual review."""

    status: HeaderDetectionStatus
    header_row: int | None = None
    candidate_rows: tuple[int, ...] = ()
    matched_columns: tuple[str, ...] = ()


def detect_header_row(header_preview: pd.DataFrame) -> HeaderDetectionResult:
    """Rank the first five rows and select only a unique, reliable candidate."""
    candidates: list[HeaderRowCandidate] = []
    preview = header_preview.iloc[:HEADER_SCAN_ROWS]

    for row_position in range(len(preview)):
        mapping_result = map_columns(
            list(preview.iloc[row_position].tolist())
        )
        target_scores: dict[str, float] = {}
        exact_targets: set[str] = set()
        for mapping in mapping_result.mappings:
            if mapping.source_index is None:
                continue
            for target, score in mapping.candidate_scores:
                target_scores[target] = max(
                    target_scores.get(target, 0.0),
                    score,
                )
                if mapping.status in (
                    MappingStatus.EXACT_MATCH,
                    MappingStatus.NORMALIZED_MATCH,
                ):
                    exact_targets.add(target)

        matched_columns = tuple(
            column for column in MANDATORY_COLUMNS if column in target_scores
        )
        if not matched_columns:
            continue
        candidates.append(
            HeaderRowCandidate(
                excel_row=row_position + 1,
                matched_columns=matched_columns,
                exact_match_count=len(exact_targets),
                similarity_score=sum(target_scores.values()),
            )
        )

    if not candidates:
        return HeaderDetectionResult(status=HeaderDetectionStatus.NOT_FOUND)

    best_rank = max(candidate.rank for candidate in candidates)
    best_candidates = tuple(
        candidate for candidate in candidates if candidate.rank == best_rank
    )
    best_candidate = best_candidates[0]
    if len(best_candidate.matched_columns) < MINIMUM_HEADER_MATCHES:
        return HeaderDetectionResult(status=HeaderDetectionStatus.NOT_FOUND)
    if len(best_candidates) > 1:
        return HeaderDetectionResult(
            status=HeaderDetectionStatus.AMBIGUOUS,
            candidate_rows=tuple(
                candidate.excel_row for candidate in best_candidates
            ),
            matched_columns=best_candidate.matched_columns,
        )
    return HeaderDetectionResult(
        status=HeaderDetectionStatus.DETECTED,
        header_row=best_candidate.excel_row,
        candidate_rows=(best_candidate.excel_row,),
        matched_columns=best_candidate.matched_columns,
    )
