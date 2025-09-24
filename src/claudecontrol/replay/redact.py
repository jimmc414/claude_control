"""Secret redaction utilities."""

from __future__ import annotations

import os
import re

SECRET_PATTERNS = (
    re.compile(r"(?i)(api[_-]?key|token|password)\s*[:=]\s*[^\s]+"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"(?i)secret[^\s]{6,}"),
)


def redact_bytes(payload: bytes) -> bytes:
    """Redact secrets in a byte payload unless opted out."""

    if os.environ.get("CLAUDECONTROL_REDACT", "1") in {"0", "false", "False"}:
        return payload

    try:
        decoded = payload.decode("utf-8")
    except UnicodeDecodeError:
        return payload

    redacted = decoded
    for pattern in SECRET_PATTERNS:
        redacted = pattern.sub(lambda match: _mask(match.group(0)), redacted)
    return redacted.encode("utf-8")


def _mask(value: str) -> str:
    if ":" in value:
        key, _, _ = value.partition(":")
        return f"{key}: ***"
    if "=" in value:
        key, _, _ = value.partition("=")
        return f"{key}=***"
    return "***"
