from __future__ import annotations

from collections.abc import Iterable, Sequence

PERSIAN_FONT_PRIORITY: tuple[str, ...] = (
    "Vazirmatn",
    "IRANSansX",
    "IRANSans",
    "Shabnam",
    "Sahel",
    "Noto Sans Arabic UI",
    "Noto Sans Arabic",
    "Noto Naskh Arabic UI",
    "Noto Naskh Arabic",
    "Noto Kufi Arabic",
    "DejaVu Sans",
)
GENERIC_UI_FALLBACK = "Sans Serif"


def resolve_ui_font_stack(
    installed_families: Iterable[str], *, limit: int = 4
) -> list[str]:
    installed = {str(name) for name in installed_families}
    selected: list[str] = []
    for family in PERSIAN_FONT_PRIORITY:
        if family in installed:
            selected.append(family)
        if len(selected) >= limit:
            break
    if not selected:
        return [GENERIC_UI_FALLBACK]
    return selected


def format_qss_font_stack(families: Sequence[str] | None) -> str:
    stack: list[str] = []
    if families:
        for family in families:
            name = str(family).strip()
            if name and name not in stack:
                stack.append(name)
    if not stack:
        stack = list(PERSIAN_FONT_PRIORITY[:4])
    if GENERIC_UI_FALLBACK not in stack:
        stack.append(GENERIC_UI_FALLBACK)
    return ", ".join(f'"{name}"' for name in stack)
