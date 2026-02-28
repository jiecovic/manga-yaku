# backend-python/core/usecases/translation/utils.py
"""Utility helpers shared across translation operations."""

from __future__ import annotations


def normalize_translation_output(text: str) -> str:
    """
    Normalize raw model output for translations.

    Currently:
    - Strip whitespace
    - Remove ONE pair of outer wrapping quotes if they cover the full string
      (handles ", ', “”, 「」, 『』)
    - Leave internal quotes untouched
    """
    s = (text or "").strip()
    if len(s) < 2:
        return s

    quote_pairs = [
        ('"', '"'),
        ("'", "'"),
        ("“", "”"),
        ("「", "」"),
        ("『", "』"),
    ]

    for left, right in quote_pairs:
        if s.startswith(left) and s.endswith(right):
            inner = s[len(left):-len(right)].strip()
            if inner:
                return inner
            return s

    return s
