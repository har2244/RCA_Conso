"""Tests for the temporary real-workbook command-line runner."""

from io import StringIO
import os
from pathlib import Path
from typing import Any, Mapping, Sequence
from datetime import date

import pytest
from openpyxl import Workbook

from config.column_schema import MANDATORY_COLUMNS
from scripts.run_real_workbook_test import main, run_real_workbook_test

REPORTING_DATE = date(2025, 3, 4)


def _row(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        column: f"value-{index}" for index, column in enumerate(MANDATORY_COLUMNS)
    }
    values["Date"] = "2025-03-04"
    values["Project"] = "LWE"
    values["Site ID"] = "00123"
    values["O&M Start (Yes/No)"] = "Yes"
    values["Outage Min."] = 15
    values.update(overrides)
    return values


def _run(workbook_paths: Sequence[Path], **kwargs: Any) -> int:
    return run_real_workbook_test(
        workbook_paths,
        reporting_date=REPORTING_DATE,
        **kwargs,
    )


def _write_workbook(
    path: Path,
    rows: Sequence[Mapping[str, object]],
    *,
    headers: Sequence[str] = MANDATORY_COLUMNS,
    header_aliases: Mapping[str, str] | None = None,
    header_row: int = 1,
    site_id_formats: Mapping[int, str] | None = None,
) -> None:
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "RCA_Data"
    for _ in range(header_row - 1):
        worksheet.append(["Workbook title"])
    worksheet.append(list(headers))
    site_id_formats = site_id_formats or {}
    site_id_column = (
        list(headers).index("Site ID") + 1
        if "Site ID" in headers
        else None
    )
    for row_position, row in enumerate(rows):
        worksheet.append(
            [
                row.get((header_aliases or {}).get(header, header))
                for header in headers
            ]
        )
        if row_position in site_id_formats and site_id_column is not None:
            worksheet.cell(
                row=worksheet.max_row,
                column=site_id_column,
            ).number_format = site_id_formats[row_position]
    workbook.save(path)


def test_processes_multiple_real_workbooks_and_reports_batch_statistics(
    tmp_path: Path,
) -> None:
    first_path = tmp_path / "first.xlsx"
    second_path = tmp_path / "second.xlsm"
    shared = _row(RCA="shared")
    _write_workbook(
        first_path,
        [_row(RCA="first"), shared],
    )
    _write_workbook(second_path, [shared])

    output = StringIO()
    exit_code = _run(
        [first_path, second_path],
        input_fn=lambda _: "",
        output=output,
    )
    report = output.getvalue()

    assert exit_code == 0
    assert "Filename: first.xlsx" in report
    assert "Filename: second.xlsm" in report
    assert report.count("Processing status: PROCESSED") == 2
    assert "Successfully processed files: 2" in report
    assert "Total input records: 3" in report
    assert "Duplicate records removed: 1" in report
    assert "Final consolidated records: 2" in report
    assert "Final schema: " + ", ".join(MANDATORY_COLUMNS) in report
    assert "Retained rows: 0" in report


def test_automatically_detects_nonfirst_header_row_and_reports_it(
    tmp_path: Path,
) -> None:
    path = tmp_path / "header-row-three.xlsx"
    _write_workbook(
        path,
        [_row(Project="LWE")],
        header_row=3,
    )
    output = StringIO()

    exit_code = _run(
        [path],
        input_fn=lambda _: "",
        output=output,
    )

    assert exit_code == 0
    assert "Excel header row: 3" in output.getvalue()
    assert "Processing status: PROCESSED" in output.getvalue()


@pytest.mark.parametrize(
    ("answer", "expected_status", "expected_text"),
    [
        ("1", "PROCESSED", "Project"),
        ("r", "MISSING_PROJECT", "Missing mandatory columns"),
    ],
)
def test_mapping_suggestions_require_explicit_approval_or_rejection(
    tmp_path: Path,
    answer: str,
    expected_status: str,
    expected_text: str,
) -> None:
    path = tmp_path / "fuzzy.xlsx"
    headers = list(MANDATORY_COLUMNS)
    headers[1] = "Projec"
    _write_workbook(
        path,
        [_row(Project="LWE")],
        headers=headers,
        header_aliases={"Projec": "Project"},
    )
    output = StringIO()

    exit_code = _run(
        [path],
        input_fn=lambda _: answer,
        output=output,
    )
    report = output.getvalue()

    assert "Source column 1: 'Projec'" in report
    assert "Suggested standard column: Project" in report
    assert expected_status in report
    assert expected_text in report
    if answer == "1":
        assert exit_code == 0
        assert "Final consolidated records: 1" in report
    else:
        assert exit_code == 1
        assert "Final consolidated records: 0" in report


def test_reports_cell_findings_and_never_changes_source_workbook(
    tmp_path: Path,
) -> None:
    path = tmp_path / "findings.xlsx"
    _write_workbook(
        path,
        [
            _row(
                Date="2025-03-04",
                Circle=None,
                **{"Site ID": 12.5},
            ),
            _row(Date="03/04/2025", RCA="unsupported-date"),
        ],
        site_id_formats={0: "000000.00"},
    )
    original_bytes = path.read_bytes()
    output = StringIO()

    exit_code = _run(
        [path],
        input_fn=lambda _: "",
        output=output,
    )

    report = output.getvalue()
    assert exit_code == 0
    assert "Blank Circle at data row 1" in report
    assert "Blank/invalid Date: 0/1" in report
    assert "Site ID format at D2" in report
    assert path.read_bytes() == original_bytes


def test_reports_missing_and_corrupt_workbooks_clearly(tmp_path: Path) -> None:
    missing_path = tmp_path / "missing.xlsx"
    corrupt_path = tmp_path / "corrupt.xlsx"
    corrupt_path.write_bytes(b"not an Excel workbook")
    output = StringIO()

    exit_code = _run(
        [missing_path, corrupt_path],
        input_fn=lambda _: "",
        output=output,
    )

    report = output.getvalue()
    assert exit_code == 1
    assert "Filename: missing.xlsx" in report
    assert "Error: File not found." in report
    assert "Filename: corrupt.xlsx" in report
    assert "Could not read worksheet 'RCA_Data'" in report
    assert "Successfully processed files: 0" in report


def test_per_file_header_rows_and_project_override_use_cli_configuration(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    dta1 = tmp_path / "dta1.xlsx"
    dta2 = tmp_path / "dta2.xlsx"
    dta1_headers = tuple(
        column for column in MANDATORY_COLUMNS if column != "Project"
    )
    row_without_project = _row()
    row_with_project = _row(Project="4G Saturation")
    _write_workbook(
        dta1,
        [row_without_project],
        headers=dta1_headers,
        header_row=3,
    )
    _write_workbook(dta2, [row_with_project], header_row=1)
    original_dta1 = dta1.read_bytes()
    original_dta2 = dta2.read_bytes()

    exit_code = main(
        [
            "--reporting-date",
            "2025-03-04",
            "--header-row",
            f"{dta1}=3",
            "--header-row",
            f"{dta2}=1",
            "--project-assignment",
            f"{dta1}=4G Saturation",
            str(dta1),
            str(dta2),
        ]
    )

    report = capsys.readouterr().out
    assert exit_code == 0
    assert "MISSING_PROJECT resolved by explicit assignment '4G Saturation'." in report
    assert "Successfully processed files: 2" in report
    assert "Total input records: 2" in report
    assert "Duplicate records removed: 1" in report
    assert "Final consolidated records: 1" in report
    assert dta1.read_bytes() == original_dta1
    assert dta2.read_bytes() == original_dta2


def test_project_assignment_does_not_fill_other_missing_mandatory_columns(
    tmp_path: Path,
) -> None:
    path = tmp_path / "missing-site-name.xlsx"
    headers = tuple(
        column
        for column in MANDATORY_COLUMNS
        if column not in ("Project", "Site Name")
    )
    _write_workbook(
        path,
        [_row()],
        headers=headers,
    )
    output = StringIO()

    exit_code = _run(
        [path],
        project_assignments_by_path={str(path): "4G Saturation"},
        input_fn=lambda _: "",
        output=output,
    )

    report = output.getvalue()
    assert exit_code == 1
    assert "Missing mandatory columns: ('Site Name',)" in report
    assert "Final consolidated records: 0" in report


def test_project_assignment_does_not_overwrite_existing_project_values(
    tmp_path: Path,
) -> None:
    path = tmp_path / "existing-project.xlsx"
    _write_workbook(path, [_row(Project="LWE")])
    output = StringIO()

    exit_code = _run(
        [path],
        project_assignments_by_path={str(path): "4G Saturation"},
        input_fn=lambda _: "",
        output=output,
    )

    report = output.getvalue()
    assert exit_code == 0
    assert "Assignment was not applied because Project already exists" in report
    assert "Project identity: CONFIRMED (LWE)" in report
    assert "Final consolidated records: 1" in report


def test_missing_project_prompts_for_an_explicit_allowed_assignment(
    tmp_path: Path,
) -> None:
    path = tmp_path / "missing-project.xlsx"
    headers = tuple(
        column for column in MANDATORY_COLUMNS if column != "Project"
    )
    _write_workbook(path, [_row()], headers=headers)
    output = StringIO()
    answers = iter(["4G Saturation"])

    exit_code = _run(
        [path],
        input_fn=lambda _: next(answers),
        output=output,
    )

    report = output.getvalue()
    assert exit_code == 0
    assert "Project column is missing" in report
    assert "Project identity: ASSIGNED (4G Saturation)" in report
    assert "Final consolidated records: 1" in report


def test_circle_match_assigns_4g_project_without_prompting(
    tmp_path: Path,
) -> None:
    path = tmp_path / "circle-assignment.xlsx"
    headers = tuple(
        column for column in MANDATORY_COLUMNS if column != "Project"
    )
    _write_workbook(
        path,
        [_row(Circle="North 4G-Satu Circle")],
        headers=headers,
    )
    original_bytes = path.read_bytes()
    output = StringIO()

    exit_code = _run(
        [path],
        input_fn=lambda _: pytest.fail("Circle assignment should not prompt."),
        output=output,
    )

    report = output.getvalue()
    assert exit_code == 0
    assert "Project identity: ASSIGNED (4G Saturation)" in report
    assert "automatically assigned as '4G Saturation' from Circle" in report
    assert "Final consolidated records: 1" in report
    assert path.read_bytes() == original_bytes


def test_missing_project_is_not_inferred_from_filename_or_included_without_assignment(
    tmp_path: Path,
) -> None:
    path = tmp_path / "LWE.xlsx"
    headers = tuple(
        column for column in MANDATORY_COLUMNS if column != "Project"
    )
    _write_workbook(path, [_row()], headers=headers)
    output = StringIO()

    exit_code = _run(
        [path],
        input_fn=lambda _: "r",
        output=output,
    )

    report = output.getvalue()
    assert exit_code == 1
    assert "Project column is missing" in report
    assert "Project identity: MISSING_PROJECT" in report
    assert "Final consolidated records: 0" in report


def test_lwe_and_4g_saturation_remain_distinguishable_in_master_dataset(
    tmp_path: Path,
) -> None:
    lwe_path = tmp_path / "lwe.xlsx"
    saturation_path = tmp_path / "saturation.xlsx"
    _write_workbook(lwe_path, [_row(Project="LWE", RCA="lwe")])
    _write_workbook(
        saturation_path,
        [_row(Project="4G Saturation", RCA="saturation")],
    )
    output = StringIO()

    exit_code = _run(
        [lwe_path, saturation_path],
        input_fn=lambda _: "",
        output=output,
    )

    report = output.getvalue()
    assert exit_code == 0
    assert "Project identity: CONFIRMED (LWE)" in report
    assert "Project identity: CONFIRMED (4G Saturation)" in report
    assert "Project counts: LWE=1, 4G Saturation=1" in report
    assert "Final consolidated records: 2" in report


@pytest.mark.parametrize(
    ("project_values", "expected_finding"),
    [
        (["Unknown Project"], "Unsupported Project values"),
        ([None], "Blank Project values"),
        (["LWE", "4G Saturation"], "Inconsistent Project values"),
    ],
)
def test_unresolved_project_values_exclude_workbook_from_consolidation(
    tmp_path: Path,
    project_values: list[object],
    expected_finding: str,
) -> None:
    path = tmp_path / "unresolved-project.xlsx"
    _write_workbook(
        path,
        [
            _row(Project=value, RCA=f"row-{index}")
            for index, value in enumerate(project_values)
        ],
    )
    output = StringIO()

    exit_code = _run(
        [path],
        input_fn=lambda _: "",
        output=output,
    )

    report = output.getvalue()
    assert exit_code == 1
    assert "Processing status: INVALID_PROJECT_VALUES" in report
    assert expected_finding in report
    assert "Successfully processed files: 0" in report
    assert "Final consolidated records: 0" in report


def test_only_approved_project_assignments_are_accepted(
    tmp_path: Path,
) -> None:
    path = tmp_path / "missing-project.xlsx"
    headers = tuple(
        column for column in MANDATORY_COLUMNS if column != "Project"
    )
    _write_workbook(path, [_row()], headers=headers)
    output = StringIO()

    exit_code = _run(
        [path],
        project_assignments_by_path={str(path): "Unknown"},
        input_fn=lambda _: "",
        output=output,
    )

    assert exit_code == 2
    assert "Project assignments must use an approved value" in output.getvalue()


@pytest.mark.parametrize("configuration_is_relative", [True, False])
def test_cli_normalizes_relative_and_absolute_workbook_configuration_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    configuration_is_relative: bool,
) -> None:
    monkeypatch.chdir(tmp_path)
    workbook_path = tmp_path / "data" / "input" / "dta1.xlsx"
    workbook_path.parent.mkdir(parents=True)
    _write_workbook(
        workbook_path,
        [_row()],
        headers=tuple(
            column for column in MANDATORY_COLUMNS if column != "Project"
        ),
        header_row=3,
    )
    relative_path = os.path.join(".", "data", "input", "dta1.xlsx")
    absolute_path = str(workbook_path.resolve())
    config_path = relative_path if configuration_is_relative else absolute_path
    workbook_argument = absolute_path if configuration_is_relative else relative_path

    exit_code = main(
        [
            "--reporting-date",
            "2025-03-04",
            "--header-row",
            f"{config_path}=3",
            "--project-assignment",
            f"{config_path}=4G Saturation",
            workbook_argument,
        ]
    )

    report = capsys.readouterr().out
    assert exit_code == 0
    assert "Processing status: PROCESSED" in report
    assert "Final consolidated records: 1" in report
    assert "Configuration refers to workbook path(s) not provided" not in report
