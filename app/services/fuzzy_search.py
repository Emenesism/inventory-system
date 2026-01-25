from __future__ import annotations

from rapidfuzz import process

from app.utils.text import normalize_text


def get_fuzzy_matches(
    query: str, choices: list[str], limit: int = 8
) -> list[str]:
    if not query or len(query.strip()) < 1:
        return []
    matches = process.extract(
        query,
        choices,
        limit=limit,
        score_cutoff=40,
        processor=normalize_text,
    )
    return [match[0] for match in matches]
