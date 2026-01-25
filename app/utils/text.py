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


def normalize_text(value: str) -> str:
    if value is None:
        return ""
    text = normalize_numeric_text(str(value))
    text = text.translate(_ARABIC_TO_PERSIAN)
    for key, replacement in _PUNCTUATION.items():
        text = text.replace(key, replacement)
    text = re.sub(r"\s+", " ", text).strip()
    return text.casefold()
