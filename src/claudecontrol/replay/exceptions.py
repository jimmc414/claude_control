"""Exceptions for the replay subsystem."""

from __future__ import annotations


class ReplayError(RuntimeError):
    """Base error for replay related failures."""


class TapeMissError(ReplayError):
    """Raised when no recorded exchange matches the current input."""


class SchemaError(ReplayError):
    """Raised when a tape fails schema validation."""


class RedactionError(ReplayError):
    """Raised when secret redaction cannot be applied safely."""
