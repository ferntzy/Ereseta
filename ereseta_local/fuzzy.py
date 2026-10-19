"""
Small, dependency-free fuzzy matching used to power the autocomplete
comboboxes (patients, physicians, medicines, addresses).
"""

from __future__ import annotations

from collections.abc import Sequence


def _is_subsequence(query: str, text: str) -> bool:
    """True if every char in query appears in order inside text (case-insensitive)."""
    q = query.lower()
    t = text.lower()
    i = 0
    for ch in t:
        if i < len(q) and ch == q[i]:
            i += 1
    return i == len(q)


def fuzzy_filter(query: str | None, candidates: Sequence[str], limit: int = 80) -> list[str]:
    """Rank candidates by how well they match *query*.

    Priority (highest first):
      1. Exact match
      2. Starts-with
      3. Substring (contains)
      4. Word-boundary starts-with (any word)
      5. Subsequence (typed chars appear in order)
    Returns a list of matching strings, best matches first.
    Empty query -> original list order.
    
    """
    if not candidates:
        return []
    q = (query or "").strip().lower()
    if not q:
        return list(candidates)

    scored: list[tuple[float, str]] = []
    for item in candidates:
        text = str(item)
        low = text.lower()

        if low == q:
            score = 500.
        elif low.startswith(q):
            score = 400.0 - min(len(low), 50)  # shorter is better among prefix hits
        elif q in low:
            # earlier occurrence + shorter string ranks higher
            pos = low.find(q)
            score = 300.0 - pos - min(len(low), 80) * 0.05
        else:
            # any word starts with query?
            words = low.replace(",", " ").replace("-", " ").split()
            if any(w.startswith(q) for w in words):
                score = 200.0
            elif _is_subsequence(q, low):
                # prefer denser matches (query length vs text length)
                density = len(q) / max(len(low), 1)
                score = 100.0 + density * 50
            else:
                continue

        scored.append((score, text))

    scored.sort(key=lambda x: (-x[0], x[1].lower()))
    return [s[1] for s in scored[:limit]]
