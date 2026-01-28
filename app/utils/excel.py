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
