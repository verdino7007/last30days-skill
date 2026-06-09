"""Shared text-processing helpers used across multiple source modules."""

import html as _html
import re
from typing import Any, Optional


def first_of(*values: Any, default: Any = None) -> Any:
    """Return the first value that is not None."""
    for v in values:
        if v is not None:
            return v
    return default


def strip_html(text: str, *, decode_entities: bool = True) -> str:
    """Strip HTML tags and optionally decode entities.

    Handles both ``<p>``-delimited content (Hacker News) and
    ``<br>``-delimited content (Truth Social / Mastodon).

    Args:
        text: Raw HTML string.
        decode_entities: If True (default), decode ``&amp;`` → ``&`` etc.
            Pass False to preserve entity references verbatim.
    """
    if not text:
        return ""
    if decode_entities:
        text = _html.unescape(text)
    text = re.sub(r'<br\s*/?>', '\n', text)
    text = re.sub(r'<p>', '\n', text)
    text = re.sub(r'<[^>]+>', '', text)
    return text.strip()
