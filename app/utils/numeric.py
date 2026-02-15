from __future__ import annotations

import math

_PERSIAN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")
_ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
_PRICE_KEYWORDS = ("price", "cost", "amount", "total", "profit", "avg_buy")
_QUANTITY_KEYWORDS = ("qty", "quantity", "count", "number")


def normalize_numeric_text(value: str) -> str:
    normalized = value.translate(_PERSIAN_DIGITS).translate(_ARABIC_DIGITS)
    normalized = normalized.replace("٬", "").replace(",", "")
    normalized = normalized.replace("٫", ".")
    return normalized.strip()


def format_amount(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        normalized = normalize_numeric_text(value)
        if not normalized:
            return ""
        try:
            number = float(normalized)
        except ValueError:
            return value
    else:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return str(value)
    if math.isnan(number):
        return ""
    return f"{number:,.0f}"


def format_number(value: object, grouping: bool = False) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, int):
        return str(value)
    number: float | None = None
    if isinstance(value, str):
        normalized = normalize_numeric_text(value)
        if not normalized:
            return value
        cleaned = normalized.lstrip("-")
        if cleaned.replace(".", "", 1).isdigit():
            try:
                number = float(normalized)
            except ValueError:
                return value
        else:
            return value
    else:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return str(value)
    if number is None or not math.isfinite(number):
        return ""
    rounded = int(round(number))
    if grouping:
        return f"{rounded:,}"
    return str(rounded)


def is_price_column(name: object) -> bool:
    if name is None:
        return False
    lowered = str(name).strip().lower()
    if not lowered:
        return False
    if any(token in lowered for token in _QUANTITY_KEYWORDS):
        return False
    return any(token in lowered for token in _PRICE_KEYWORDS)
