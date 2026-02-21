from __future__ import annotations

import re

from app.utils.numeric import normalize_numeric_text

_ARABIC_TO_PERSIAN = str.maketrans(
    {
        "ي": "ی",
        "ك": "ک",
        "ة": "ه",
        "ۀ": "ه",
        "ؤ": "و",
        "أ": "ا",
        "إ": "ا",
        "ٱ": "ا",
        "آ": "ا",
        "ئ": "ی",
    }
)

_PUNCTUATION = {
    "،": " ",
    ",": " ",
    "؛": " ",
    ";": " ",
    ":": " ",
    ".": " ",
    "ـ": " ",
    "‌": " ",  # ZWNJ
    "\u200c": " ",
    "\u200d": " ",
}
_EMPTY_MARKERS = {"nan", "none", "<na>", "nat", "null"}


def normalize_text(value: str) -> str:
    if value is None:
        return ""
    text = normalize_numeric_text(str(value))
    text = text.translate(_ARABIC_TO_PERSIAN)
    for key, replacement in _PUNCTUATION.items():
        text = text.replace(key, replacement)
    text = re.sub(r"\s+", " ", text).strip()
    return text.casefold()


def is_empty_marker(value: object) -> bool:
    if value is None:
        return True
    try:
        compare = value != value
        if isinstance(compare, bool) and compare:
            return True
        if (
            not isinstance(compare, bool)
            and str(compare).strip().casefold() == "true"
        ):
            return True
    except Exception:  # noqa: BLE001
        pass
    text = str(value).strip()
    if not text:
        return True
    return text.casefold() in _EMPTY_MARKERS


def display_text(value: object, fallback: str = "") -> str:
    if is_empty_marker(value):
        return fallback
    return str(value).strip()
