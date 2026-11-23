"""Apply the RCA master-workbook presentation to an Excel worksheet."""

from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.worksheet.filters import AutoFilter
from openpyxl.worksheet.table import Table, TableStyleInfo
from openpyxl.worksheet.worksheet import Worksheet

from config.column_schema import MANDATORY_COLUMNS


HEADER_BLUE = "12345A"
LIGHT_BLUE = "DDEBF7"
WHITE = "FFFFFF"
BLACK = "000000"
TABLE_NAME = "RCADataTable"

_COLUMN_WIDTHS = {
    "Date": 16,
    "Project": 20,
    "Circle": 18,
    "Site ID": 16,
    "Site Name": 28,
    "OA": 12,
    "BA": 12,
    "O&M Start (Yes/No)": 22,
    "Outage Min.": 16,
    "Final Bucket": 26,
    "Bucket - 2": 30,
    "RCA": 50,
}


def format_rca_worksheet(worksheet: Worksheet) -> None:
    """Style all RCA rows and add a filterable, banded Excel Table."""
    headers = tuple(
        worksheet.cell(row=1, column=column_index).value
        for column_index in range(1, len(MANDATORY_COLUMNS) + 1)
    )
    if worksheet.max_column != len(MANDATORY_COLUMNS) or headers != MANDATORY_COLUMNS:
        raise ValueError(
            "RCA worksheet must contain the 12 mandatory columns in schema order."
        )

    thin_black = Side(style="thin", color=BLACK)
    cell_border = Border(
        left=thin_black,
        right=thin_black,
        top=thin_black,
        bottom=thin_black,
    )
    header_fill = PatternFill(fill_type="solid", fgColor=HEADER_BLUE)
    white_fill = PatternFill(fill_type="solid", fgColor=WHITE)
    light_blue_fill = PatternFill(fill_type="solid", fgColor=LIGHT_BLUE)

    worksheet.freeze_panes = "A2"
    worksheet.row_dimensions[1].height = 36
    worksheet.sheet_view.showGridLines = False

    for column_index, column_name in enumerate(MANDATORY_COLUMNS, start=1):
        worksheet.column_dimensions[
            worksheet.cell(row=1, column=column_index).column_letter
        ].width = _COLUMN_WIDTHS[column_name]
        header_cell = worksheet.cell(row=1, column=column_index)
        header_cell.fill = header_fill
        header_cell.font = Font(name="Arial", size=10, bold=True, color=WHITE)
        header_cell.alignment = Alignment(
            horizontal="center",
            vertical="center",
            wrap_text=True,
        )
        header_cell.border = cell_border

    for row_index in range(2, worksheet.max_row + 1):
        worksheet.row_dimensions[row_index].height = 30
        row_fill = white_fill if row_index % 2 == 0 else light_blue_fill
        for column_index, column_name in enumerate(MANDATORY_COLUMNS, start=1):
            cell = worksheet.cell(row=row_index, column=column_index)
            cell.fill = row_fill
            cell.border = cell_border
            cell.font = Font(name="Arial", size=10, color=BLACK)
            cell.alignment = Alignment(
                horizontal=(
                    "right"
                    if column_name == "Outage Min."
                    else "center"
                    if column_name in ("Date", "Site ID", "O&M Start (Yes/No)")
                    else "left"
                ),
                vertical="center",
                wrap_text=True,
            )
            if column_name == "Date":
                cell.number_format = "dd-mmm-yyyy"
            elif column_name == "Site ID":
                cell.number_format = "@"
            elif column_name == "Outage Min.":
                cell.number_format = "0.##"

    table_reference = f"A1:L{max(worksheet.max_row, 1)}"
    table = Table(displayName=TABLE_NAME, ref=table_reference)
    table.autoFilter = AutoFilter(ref=table_reference)
    table.tableStyleInfo = TableStyleInfo(
        name="TableStyleMedium2",
        showFirstColumn=False,
        showLastColumn=False,
        showRowStripes=True,
        showColumnStripes=False,
    )
    worksheet.add_table(table)