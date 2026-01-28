from __future__ import annotations

from rapidfuzz import process

from app.utils.text import normalize_text


def get_fuzzy_matches(
    query: str, choices: list[str], limit: int = 20
) -> list[str]:
    if not query or len(query.strip()) < 1 or not choices:
        return []

    normalized_query = normalize_text(query)
    if not normalized_query:
        return []

    exact: list[str] = []
    starts: list[str] = []
    contains: list[str] = []
    remaining: list[str] = []

    for choice in choices:
        normalized_choice = normalize_text(choice)
        if not normalized_choice:
            continue
        if normalized_choice == normalized_query:
            exact.append(choice)
        elif normalized_choice.startswith(normalized_query):
            starts.append(choice)
        elif normalized_query in normalized_choice:
            contains.append(choice)
        else:
            remaining.append(choice)

    ordered = exact + starts + contains
    seen = set(ordered)

    fuzzy_matches: list[str] = []
    if remaining:
        matches = process.extract(
            query,
            remaining,
            limit=limit,
            score_cutoff=30,
            processor=normalize_text,
        )
        for match in matches:
            candidate = match[0]
            if candidate not in seen:
                fuzzy_matches.append(candidate)
                seen.add(candidate)

    return ordered + fuzzy_matches
