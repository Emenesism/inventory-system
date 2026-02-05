from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QMarginsF, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QPageLayout,
    QPageSize,
    QPainter,
    QPen,
)
from PySide6.QtPrintSupport import QPrinter

from app.utils.dates import to_jalali_datetime
from app.utils.excel import _aggregate_invoice_lines
from app.utils.numeric import format_amount


def export_invoice_pdf(file_path: str | Path, invoice, lines) -> None:
    export_invoices_pdf(file_path, [(invoice, lines)])


def export_invoices_pdf(file_path: str | Path, invoices_with_lines) -> None:
    if not invoices_with_lines:
        return
    try:
        printer = QPrinter(QPrinter.HighResolution)
        printer.setOutputFormat(QPrinter.PdfFormat)
        printer.setOutputFileName(str(file_path))
        printer.setPageSize(QPageSize(QPageSize.A4))
        printer.setPageOrientation(QPageLayout.Portrait)
        printer.setPageMargins(
            QMarginsF(12, 12, 12, 12), QPageLayout.Millimeter
        )
    except Exception:  # noqa: BLE001
        return

    painter = QPainter()
    if not painter.begin(printer):
        return

    for idx, (invoice, lines) in enumerate(invoices_with_lines):
        if idx > 0:
            printer.newPage()
        _draw_invoice_pdf(painter, printer, invoice, lines)

    painter.end()


def _draw_invoice_pdf(
    painter: QPainter, printer: QPrinter, invoice, lines
) -> None:
    from datetime import datetime
    from zoneinfo import ZoneInfo

    hide_prices = str(invoice.invoice_type or "").startswith("sales")
    title_text = _invoice_title(invoice)
    invoice_type_text = _invoice_type_label(invoice)

    export_dt = datetime.now(ZoneInfo("Asia/Tehran"))
    export_date = to_jalali_datetime(
        export_dt.isoformat(timespec="seconds")
    ).split(" ")[0]
    invoice_date = to_jalali_datetime(invoice.created_at).split(" ")[0]

    merged_lines = _aggregate_invoice_lines(lines)
    total_qty = sum(int(line["quantity"]) for line in merged_lines)
    total_amount = sum(float(line["total_amount"]) for line in merged_lines)

    title_font = QFont("Vazirmatn", 18, QFont.Bold)
    header_font = QFont("Vazirmatn", 11, QFont.Bold)
    body_font = QFont("Vazirmatn", 11)
    label_font = QFont("Vazirmatn", 10, QFont.Bold)

    title_metrics = QFontMetrics(title_font)
    header_metrics = QFontMetrics(header_font)
    body_metrics = QFontMetrics(body_font)

    title_height = max(32, int(title_metrics.height() * 1.6))
    info_row_height = max(22, int(body_metrics.height() * 1.5))
    header_row_height = max(24, int(header_metrics.height() * 1.6))
    row_height = max(24, int(body_metrics.height() * 1.7))
    section_gap = max(8, int(row_height * 0.35))
    cell_padding = max(6, int(row_height * 0.25))

    header_fill = QColor("#E8F3E1")
    stripe_fill = QColor("#F7F9FC")
    total_fill = QColor("#EEF2FF")
    border_color = QColor("#C7CED6")
    text_color = QColor("#111827")

    col_weights = [6, 38, 10, 14, 16]

    page_rect = printer.pageRect()
    x0 = float(page_rect.x())
    y0 = float(page_rect.y())
    content_width = float(page_rect.width())
    content_height = float(page_rect.height())

    col_widths = _scale_columns(content_width, col_weights)
    col_lefts = _column_lefts(x0, content_width, col_widths)

    painter.setPen(QPen(border_color, 1))
    painter.setRenderHint(QPainter.Antialiasing, False)

    start_index = 0
    while start_index < len(merged_lines) or start_index == 0:
        y = y0
        _draw_title(
            painter,
            QRectF(x0, y, content_width, title_height),
            title_text,
            title_font,
            text_color,
        )
        y += title_height + section_gap

        _draw_header_info(
            painter,
            y,
            info_row_height,
            col_lefts,
            col_widths,
            label_font,
            body_font,
            text_color,
            [
                ("تاریخ فاکتور:", invoice_date, "تاریخ خروجی:", export_date),
                (
                    "شماره فاکتور:",
                    str(invoice.invoice_id),
                    "نوع:",
                    invoice_type_text,
                ),
            ],
            cell_padding,
        )
        y += info_row_height * 2 + section_gap

        y = _draw_table_header(
            painter,
            y,
            header_row_height,
            col_lefts,
            col_widths,
            header_font,
            text_color,
            border_color,
            header_fill,
            hide_prices,
            cell_padding,
        )

        table_bottom = y0 + content_height
        available_rows = int((table_bottom - y) // row_height)
        if available_rows <= 0:
            available_rows = 1

        remaining = len(merged_lines) - start_index
        draw_totals = remaining + 1 <= available_rows
        lines_on_page = remaining if draw_totals else available_rows

        for offset in range(lines_on_page):
            row_idx = start_index + offset
            line = merged_lines[row_idx]
            y = _draw_table_row(
                painter,
                y,
                row_height,
                col_lefts,
                col_widths,
                body_font,
                text_color,
                border_color,
                stripe_fill if (row_idx + 1) % 2 == 0 else None,
                hide_prices,
                row_idx + 1,
                line,
                cell_padding,
            )

        start_index += lines_on_page

        if draw_totals:
            _draw_totals_row(
                painter,
                y,
                row_height,
                col_lefts,
                col_widths,
                header_font,
                text_color,
                border_color,
                total_fill,
                hide_prices,
                total_qty,
                total_amount,
                cell_padding,
            )
            break

        printer.newPage()


def _invoice_title(invoice) -> str:
    if invoice.invoice_type == "sales_manual":
        return "فاکتور فروش دستی"
    return (
        "فاکتور فروش"
        if str(invoice.invoice_type).startswith("sales")
        else "فاکتور خرید"
    )


def _invoice_type_label(invoice) -> str:
    if invoice.invoice_type == "sales_manual":
        return "فروش دستی"
    return "فروش" if str(invoice.invoice_type).startswith("sales") else "خرید"


def _scale_columns(total_width: float, weights: list[int]) -> list[float]:
    total = float(sum(weights))
    if total <= 0:
        return [total_width]
    return [total_width * (weight / total) for weight in weights]


def _column_lefts(
    x0: float, total_width: float, widths: list[float]
) -> list[float]:
    lefts: list[float] = []
    cursor = x0 + total_width
    for width in widths:
        cursor -= width
        lefts.append(cursor)
    return lefts


def _draw_title(
    painter: QPainter,
    rect: QRectF,
    text: str,
    font: QFont,
    text_color: QColor,
) -> None:
    painter.setFont(font)
    painter.setPen(text_color)
    painter.drawText(rect, Qt.AlignCenter, text)


def _draw_header_info(
    painter: QPainter,
    start_y: float,
    row_height: float,
    col_lefts: list[float],
    col_widths: list[float],
    label_font: QFont,
    body_font: QFont,
    text_color: QColor,
    rows: list[tuple[str, str, str, str]],
    padding: int,
) -> None:
    for row_idx, (label_a, value_a, label_b, value_b) in enumerate(rows):
        y = start_y + row_idx * row_height
        _draw_text(
            painter,
            QRectF(col_lefts[0], y, col_widths[0], row_height),
            label_a,
            label_font,
            Qt.AlignRight,
            text_color,
            padding,
        )
        _draw_text(
            painter,
            QRectF(col_lefts[1], y, col_widths[1], row_height),
            value_a,
            body_font,
            Qt.AlignRight,
            text_color,
            padding,
        )
        _draw_text(
            painter,
            QRectF(col_lefts[3], y, col_widths[3], row_height),
            label_b,
            label_font,
            Qt.AlignRight,
            text_color,
            padding,
        )
        _draw_text(
            painter,
            QRectF(col_lefts[4], y, col_widths[4], row_height),
            value_b,
            body_font,
            Qt.AlignRight,
            text_color,
            padding,
        )


def _draw_table_header(
    painter: QPainter,
    y: float,
    row_height: float,
    col_lefts: list[float],
    col_widths: list[float],
    header_font: QFont,
    text_color: QColor,
    border_color: QColor,
    fill: QColor,
    hide_prices: bool,
    padding: int,
) -> float:
    if hide_prices:
        merged_rect = _merge_rect(col_lefts, col_widths, 1, 3, y, row_height)
        _draw_cell(
            painter,
            QRectF(col_lefts[0], y, col_widths[0], row_height),
            "ردیف",
            header_font,
            Qt.AlignCenter,
            fill,
            border_color,
            text_color,
            padding,
        )
        _draw_cell(
            painter,
            merged_rect,
            "شرح کالا",
            header_font,
            Qt.AlignCenter,
            fill,
            border_color,
            text_color,
            padding,
        )
        _draw_cell(
            painter,
            QRectF(col_lefts[4], y, col_widths[4], row_height),
            "تعداد",
            header_font,
            Qt.AlignCenter,
            fill,
            border_color,
            text_color,
            padding,
        )
    else:
        headers = ["ردیف", "شرح کالا", "تعداد", "مبلغ واحد", "مبلغ کل"]
        aligns = [
            Qt.AlignCenter,
            Qt.AlignCenter,
            Qt.AlignCenter,
            Qt.AlignCenter,
            Qt.AlignCenter,
        ]
        for idx, title in enumerate(headers):
            _draw_cell(
                painter,
                QRectF(col_lefts[idx], y, col_widths[idx], row_height),
                title,
                header_font,
                aligns[idx],
                fill,
                border_color,
                text_color,
                padding,
            )
    return y + row_height


def _draw_table_row(
    painter: QPainter,
    y: float,
    row_height: float,
    col_lefts: list[float],
    col_widths: list[float],
    body_font: QFont,
    text_color: QColor,
    border_color: QColor,
    fill: QColor | None,
    hide_prices: bool,
    index: int,
    line: dict[str, float | int | str],
    padding: int,
) -> float:
    if hide_prices:
        merged_rect = _merge_rect(col_lefts, col_widths, 1, 3, y, row_height)
        _draw_cell(
            painter,
            QRectF(col_lefts[0], y, col_widths[0], row_height),
            str(index),
            body_font,
            Qt.AlignCenter,
            fill,
            border_color,
            text_color,
            padding,
        )
        _draw_cell(
            painter,
            merged_rect,
            str(line["product_name"]),
            body_font,
            Qt.AlignRight,
            fill,
            border_color,
            text_color,
            padding,
        )
        _draw_cell(
            painter,
            QRectF(col_lefts[4], y, col_widths[4], row_height),
            str(int(line["quantity"])),
            body_font,
            Qt.AlignCenter,
            fill,
            border_color,
            text_color,
            padding,
        )
    else:
        values = [
            str(index),
            str(line["product_name"]),
            str(int(line["quantity"])),
            format_amount(line["unit_price"]),
            format_amount(line["total_amount"]),
        ]
        aligns = [
            Qt.AlignCenter,
            Qt.AlignRight,
            Qt.AlignCenter,
            Qt.AlignCenter,
            Qt.AlignCenter,
        ]
        for idx, value in enumerate(values):
            _draw_cell(
                painter,
                QRectF(col_lefts[idx], y, col_widths[idx], row_height),
                value,
                body_font,
                aligns[idx],
                fill,
                border_color,
                text_color,
                padding,
            )
    return y + row_height


def _draw_totals_row(
    painter: QPainter,
    y: float,
    row_height: float,
    col_lefts: list[float],
    col_widths: list[float],
    header_font: QFont,
    text_color: QColor,
    border_color: QColor,
    fill: QColor,
    hide_prices: bool,
    total_qty: int,
    total_amount: float,
    padding: int,
) -> None:
    if hide_prices:
        merged_rect = _merge_rect(col_lefts, col_widths, 1, 3, y, row_height)
        _draw_cell(
            painter,
            QRectF(col_lefts[0], y, col_widths[0], row_height),
            "",
            header_font,
            Qt.AlignCenter,
            fill,
            border_color,
            text_color,
            padding,
        )
        _draw_cell(
            painter,
            merged_rect,
            "جمع کل",
            header_font,
            Qt.AlignRight,
            fill,
            border_color,
            text_color,
            padding,
        )
        _draw_cell(
            painter,
            QRectF(col_lefts[4], y, col_widths[4], row_height),
            str(total_qty),
            header_font,
            Qt.AlignCenter,
            fill,
            border_color,
            text_color,
            padding,
        )
    else:
        _draw_cell(
            painter,
            QRectF(col_lefts[0], y, col_widths[0], row_height),
            "",
            header_font,
            Qt.AlignCenter,
            fill,
            border_color,
            text_color,
            padding,
        )
        _draw_cell(
            painter,
            QRectF(col_lefts[1], y, col_widths[1], row_height),
            "جمع کل",
            header_font,
            Qt.AlignRight,
            fill,
            border_color,
            text_color,
            padding,
        )
        _draw_cell(
            painter,
            QRectF(col_lefts[2], y, col_widths[2], row_height),
            str(total_qty),
            header_font,
            Qt.AlignCenter,
            fill,
            border_color,
            text_color,
            padding,
        )
        _draw_cell(
            painter,
            QRectF(col_lefts[3], y, col_widths[3], row_height),
            "",
            header_font,
            Qt.AlignCenter,
            fill,
            border_color,
            text_color,
            padding,
        )
        _draw_cell(
            painter,
            QRectF(col_lefts[4], y, col_widths[4], row_height),
            format_amount(total_amount),
            header_font,
            Qt.AlignCenter,
            fill,
            border_color,
            text_color,
            padding,
        )


def _merge_rect(
    col_lefts: list[float],
    col_widths: list[float],
    start_idx: int,
    end_idx: int,
    y: float,
    height: float,
) -> QRectF:
    left = min(col_lefts[start_idx], col_lefts[end_idx])
    right = max(
        col_lefts[start_idx] + col_widths[start_idx],
        col_lefts[end_idx] + col_widths[end_idx],
    )
    for idx in range(start_idx, end_idx + 1):
        left = min(left, col_lefts[idx])
        right = max(right, col_lefts[idx] + col_widths[idx])
    return QRectF(left, y, right - left, height)


def _draw_cell(
    painter: QPainter,
    rect: QRectF,
    text: str,
    font: QFont,
    align: Qt.AlignmentFlag,
    fill: QColor | None,
    border_color: QColor,
    text_color: QColor,
    padding: int,
) -> None:
    if fill is not None:
        painter.fillRect(rect, fill)
    painter.setPen(QPen(border_color, 1))
    painter.drawRect(rect)
    painter.setFont(font)
    painter.setPen(text_color)
    text_rect = rect.adjusted(padding, 0, -padding, 0)
    painter.drawText(
        text_rect, align | Qt.AlignVCenter | Qt.TextSingleLine, text
    )


def _draw_text(
    painter: QPainter,
    rect: QRectF,
    text: str,
    font: QFont,
    align: Qt.AlignmentFlag,
    text_color: QColor,
    padding: int,
) -> None:
    painter.setFont(font)
    painter.setPen(text_color)
    text_rect = rect.adjusted(padding, 0, -padding, 0)
    painter.drawText(
        text_rect, align | Qt.AlignVCenter | Qt.TextSingleLine, text
    )
