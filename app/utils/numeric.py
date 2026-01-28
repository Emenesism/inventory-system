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


def is_price_column(name: object) -> bool:
    if name is None:
        return False
    lowered = str(name).strip().lower()
    if not lowered:
        return False
    if any(token in lowered for token in _QUANTITY_KEYWORDS):
        return False
    return any(token in lowered for token in _PRICE_KEYWORDS)
