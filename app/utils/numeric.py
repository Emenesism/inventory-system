from __future__ import annotations

_PERSIAN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")
_ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")


def normalize_numeric_text(value: str) -> str:
    normalized = value.translate(_PERSIAN_DIGITS).translate(_ARABIC_DIGITS)
    normalized = normalized.replace("٬", "").replace(",", "")
    normalized = normalized.replace("٫", ".")
    return normalized.strip()
