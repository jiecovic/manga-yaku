# backend-python/infra/text_utils.py
"""Shared text truncation helpers for logs, snippets, and summaries."""

from __future__ import annotations

from typing import Any


def truncate_text(
    value: Any,
    *,
    limit: int,
    collapse_whitespace: bool = False,
) -> str:
    """Return a bounded string with optional whitespace normalization."""
    raw_text = str(value or "")
    text = " ".join(raw_text.split()) if collapse_whitespace else raw_text.strip()
    if len(text) <= limit:
        return text
    if limit <= 3:
        return text[:limit]
    return f"{text[: limit - 3].rstrip()}..."


def make_snippet(value: Any, *, limit: int = 80) -> str:
    """Return a compact single-line snippet."""
    return truncate_text(value, limit=limit, collapse_whitespace=True)
