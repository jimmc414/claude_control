"""Normalization helpers for matching and diffing."""

from __future__ import annotations

import re
from typing import Iterable

ANSI_RE = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")
VOLATILE_PATTERNS: Iterable[tuple[re.Pattern[str], str]] = (
    (re.compile(r"\b\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:\.\d+)?\b"), "<TS>"),
    (re.compile(r"\b0x[0-9a-fA-F]+\b"), "<HEX>"),
    (re.compile(r"\b[0-9a-f]{7,40}\b"), "<ID>"),
)


def strip_ansi(value: str) -> str:
    """Remove ANSI escape sequences."""

    return ANSI_RE.sub("", value)


def collapse_ws(value: str) -> str:
    """Collapse whitespace to ease comparisons."""

    return re.sub(r"\s+", " ", value).strip()


def scrub(value: str) -> str:
    """Replace volatile substrings with stable placeholders."""

    result = value
    for pattern, replacement in VOLATILE_PATTERNS:
        result = pattern.sub(replacement, result)
    return result
