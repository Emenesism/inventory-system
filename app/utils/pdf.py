from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QMarginsF, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontDatabase,
    QFontMetricsF,
    QPageLayout,
    QPageSize,
    QPainter,
    QPen,
)
from PySide6.QtPrintSupport import QPrinter

from app.ui.fonts import resolve_export_font_roles
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
        printer.setPageMargins(QMarginsF(0, 0, 0, 0), QPageLayout.Millimeter)
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
    invoice_name = str(getattr(invoice, "invoice_name", "") or "").strip()

    merged_lines = _aggregate_invoice_lines(lines)
    total_qty = sum(int(line["quantity"]) for line in merged_lines)
    total_amount = sum(float(line["total_amount"]) for line in merged_lines)

    font_roles = resolve_export_font_roles(QFontDatabase.families())

    title_font = QFont(font_roles["title"], 18)
    title_font.setWeight(QFont.ExtraBold)

    header_font = QFont(font_roles["header"], 11)
    header_font.setWeight(QFont.DemiBold)

    body_font = QFont(font_roles["body"], 11)
    product_font = QFont(font_roles["product"], 10)

    label_font = QFont(font_roles["label"], 10)
    label_font.setWeight(QFont.DemiBold)

    def _font_height(font: QFont) -> float:
        return QFontMetricsF(font, painter.device()).height()

    title_height = max(36, int(_font_height(title_font) * 1.6))
    info_row_height = max(22, int(_font_height(body_font) * 1.6))
    header_row_height = max(24, int(_font_height(header_font) * 1.7))
    row_height = max(24, int(_font_height(body_font) * 1.8))
    section_gap = max(8, int(row_height * 0.35))
    cell_padding = max(6, int(row_height * 0.25))

    header_fill = QColor("#E8F3E1")
    stripe_fill = QColor("#F7F9FC")
    total_fill = QColor("#EEF2FF")
    border_color = QColor("#C7CED6")
    text_color = QColor("#111827")
    header_band_fill = QColor("#EEF2FF")
    header_card_fill = QColor("#F8FAFC")
    header_divider = QColor("#E2E8F0")
    label_color = QColor("#6B7280")

    col_weights = [6, 38, 10, 14, 16]

    page_layout = printer.pageLayout()
    full_rect = page_layout.fullRectPixels(printer.resolution())
    base_x = float(full_rect.x())
    base_y = float(full_rect.y())
    base_width = float(full_rect.width())
    base_height = float(full_rect.height())
    horizontal_scale = 0.95
    content_width = base_width * horizontal_scale
    content_height = base_height
    x0 = base_x + (base_width - content_width) / 2
    y0 = base_y

    col_widths = _scale_columns(content_width, col_weights)
    col_lefts = _column_lefts(x0, content_width, col_widths)

    painter.setPen(QPen(border_color, 1))
    painter.setRenderHint(QPainter.Antialiasing, False)
    painter.setRenderHint(QPainter.TextAntialiasing, True)

    start_index = 0
    while start_index < len(merged_lines) or start_index == 0:
        y = y0
        if start_index == 0:
            band_height = title_height + max(6, int(title_height * 0.2))
            band_rect = QRectF(x0, y, content_width, band_height)
            painter.fillRect(band_rect, header_band_fill)
            _draw_title(
                painter,
                band_rect,
                title_text,
                title_font,
                text_color,
            )
            accent_y = band_rect.bottom() - max(2, int(band_height * 0.08))
            painter.setPen(QPen(border_color, 2))
            painter.drawLine(
                x0 + content_width * 0.2,
                accent_y,
                x0 + content_width * 0.8,
                accent_y,
            )
            y += band_height + section_gap

            header_rows = [
                (
                    "تاریخ فاکتور:",
                    invoice_date,
                    "تاریخ خروجی:",
                    export_date,
                ),
                (
                    "شماره فاکتور:",
                    str(invoice.invoice_id),
                    "نوع:",
                    invoice_type_text,
                ),
                ("نام فاکتور:", invoice_name, "", ""),
            ]
            card_padding = max(6, int(row_height * 0.25))
            card_height = info_row_height * len(header_rows) + card_padding * 2
            card_rect = QRectF(x0, y, content_width, card_height)
            painter.setPen(QPen(header_divider, 1))
            painter.setBrush(header_card_fill)
            painter.drawRoundedRect(card_rect, 6, 6)
            painter.setBrush(Qt.NoBrush)
            _draw_header_info(
                painter,
                y + card_padding,
                info_row_height,
                x0,
                content_width,
                label_font,
                body_font,
                label_color,
                text_color,
                header_divider,
                header_rows,
                cell_padding,
            )
            y += card_height + section_gap

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
                product_font,
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
    x0: float,
    content_width: float,
    label_font: QFont,
    body_font: QFont,
    label_color: QColor,
    value_color: QColor,
    divider_color: QColor,
    rows: list[tuple[str, str, str, str]],
    padding: int,
) -> None:
    center_gap = max(12, int(row_height * 0.4))
    group_width = (content_width - center_gap) / 2
    label_ratio = 0.38
    label_width = group_width * label_ratio
    value_width = group_width - label_width

    left_group_left = x0
    right_group_left = x0 + group_width + center_gap
    center_x = x0 + group_width + (center_gap / 2)

    painter.setPen(QPen(divider_color, 1))
    painter.drawLine(
        center_x,
        start_y,
        center_x,
        start_y + row_height * len(rows),
    )
    if len(rows) > 1:
        for idx in range(1, len(rows)):
            painter.drawLine(
                x0 + padding,
                start_y + row_height * idx,
                x0 + content_width - padding,
                start_y + row_height * idx,
            )

    for row_idx, (label_a, value_a, label_b, value_b) in enumerate(rows):
        y = start_y + row_idx * row_height
        _draw_text(
            painter,
            QRectF(
                right_group_left + group_width - label_width,
                y,
                label_width,
                row_height,
            ),
            label_a,
            label_font,
            Qt.AlignRight,
            label_color,
            padding,
        )
        _draw_text(
            painter,
            QRectF(right_group_left, y, value_width, row_height),
            value_a,
            body_font,
            Qt.AlignRight,
            value_color,
            padding,
        )
        _draw_text(
            painter,
            QRectF(
                left_group_left + group_width - label_width,
                y,
                label_width,
                row_height,
            ),
            label_b,
            label_font,
            Qt.AlignRight,
            label_color,
            padding,
        )
        _draw_text(
            painter,
            QRectF(left_group_left, y, value_width, row_height),
            value_b,
            body_font,
            Qt.AlignRight,
            value_color,
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
    product_font: QFont,
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
            product_font,
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
            font = product_font if idx == 1 else body_font
            _draw_cell(
                painter,
                QRectF(col_lefts[idx], y, col_widths[idx], row_height),
                value,
                font,
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
