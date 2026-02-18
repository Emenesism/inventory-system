from __future__ import annotations

from collections.abc import Iterable, Sequence

PERSIAN_FONT_PRIORITY: tuple[str, ...] = (
    "Ravi",
    "Ravi Medium",
    "Ravi SemiBold",
    "Ravi ExtraBold",
    "Ravi Thin",
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
GENERIC_HTML_FALLBACK = "sans-serif"

EXPORT_TITLE_FONT_PRIORITY: tuple[str, ...] = (
    "Ravi ExtraBold",
    "Ravi SemiBold",
    "Ravi Medium",
    "Ravi",
    "Vazirmatn",
    "IRANSansX",
    "IRANSans",
)
EXPORT_HEADER_FONT_PRIORITY: tuple[str, ...] = (
    "Ravi SemiBold",
    "Ravi Medium",
    "Ravi",
    "Vazirmatn",
    "IRANSansX",
    "IRANSans",
)
EXPORT_BODY_FONT_PRIORITY: tuple[str, ...] = (
    "Ravi",
    "Ravi Medium",
    "Ravi SemiBold",
    "Vazirmatn",
    "IRANSansX",
    "IRANSans",
)
HTML_FONT_PRIORITY: tuple[str, ...] = (
    "Ravi",
    "Ravi Medium",
    "Ravi SemiBold",
    "Tahoma",
    "Segoe UI",
)


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


def resolve_font_family(
    preferred_families: Sequence[str],
    installed_families: Iterable[str] | None = None,
    *,
    fallback: str = GENERIC_UI_FALLBACK,
) -> str:
    installed: set[str] | None = None
    if installed_families is not None:
        installed = {
            str(name).strip()
            for name in installed_families
            if str(name).strip()
        }
    seen: set[str] = set()
    for family in preferred_families:
        name = str(family).strip()
        if not name or name in seen:
            continue
        seen.add(name)
        if installed is None or name in installed:
            return name
    return fallback


def resolve_export_font_roles(
    installed_families: Iterable[str] | None = None,
) -> dict[str, str]:
    body = resolve_font_family(
        EXPORT_BODY_FONT_PRIORITY, installed_families
    )
    header = resolve_font_family(
        EXPORT_HEADER_FONT_PRIORITY, installed_families, fallback=body
    )
    title = resolve_font_family(
        EXPORT_TITLE_FONT_PRIORITY, installed_families, fallback=header
    )
    return {
        "title": title,
        "header": header,
        "label": header,
        "body": body,
        "product": body,
    }


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


def format_html_font_stack(families: Sequence[str] | None = None) -> str:
    stack: list[str] = []
    source = families if families else HTML_FONT_PRIORITY
    for family in source:
        name = str(family).strip()
        if name and name not in stack:
            stack.append(name)
    if not stack:
        stack = list(HTML_FONT_PRIORITY)
    for fallback in ("Tahoma", "Segoe UI"):
        if fallback not in stack:
            stack.append(fallback)
    rendered = [f'"{name}"' for name in stack]
    rendered.append(GENERIC_HTML_FALLBACK)
    return ", ".join(rendered)
