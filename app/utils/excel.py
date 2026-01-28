from __future__ import annotations

from pathlib import Path


def _ensure_sheet_direction(path: str | Path, right_to_left: bool) -> None:
    try:
        from openpyxl import load_workbook
    except ImportError:
        return
    try:
        workbook = load_workbook(path)
    except Exception:  # noqa: BLE001
        return
    for worksheet in workbook.worksheets:
        worksheet.sheet_view.rightToLeft = right_to_left
    try:
        workbook.save(path)
    except Exception:  # noqa: BLE001
        return


def ensure_sheet_ltr(path: str | Path) -> None:
    _ensure_sheet_direction(path, right_to_left=False)


def ensure_sheet_rtl(path: str | Path) -> None:
    _ensure_sheet_direction(path, right_to_left=True)


def apply_banded_rows(
    path: str | Path, header_row: int = 1, stripe_color: str = "F7F9FC"
) -> None:
    try:
        from openpyxl import load_workbook
        from openpyxl.styles import PatternFill
    except ImportError:
        return
    try:
        workbook = load_workbook(path)
    except Exception:  # noqa: BLE001
        return
    stripe_fill = PatternFill(
        start_color=stripe_color,
        end_color=stripe_color,
        fill_type="solid",
    )
    for worksheet in workbook.worksheets:
        max_row = worksheet.max_row or 0
        max_col = worksheet.max_column or 0
        if max_row <= header_row or max_col < 1:
            continue
        start_row = header_row + 1
        for row_idx in range(start_row, max_row + 1):
            if (row_idx - start_row) % 2 == 0:
                for col_idx in range(1, max_col + 1):
                    worksheet.cell(
                        row=row_idx, column=col_idx
                    ).fill = stripe_fill
    try:
        workbook.save(path)
    except Exception:  # noqa: BLE001
        return
