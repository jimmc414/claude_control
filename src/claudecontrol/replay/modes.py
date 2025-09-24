"""Record and fallback modes mirroring Talkback semantics."""

from __future__ import annotations

from enum import Enum
from typing import Callable, Protocol, TypeVar


class RecordMode(Enum):
    """Controls how new exchanges are persisted."""

    NEW = "new"
    OVERWRITE = "overwrite"
    DISABLED = "disabled"


class FallbackMode(Enum):
    """Controls behaviour when no recorded exchange is found."""

    NOT_FOUND = "not_found"
    PROXY = "proxy"


T = TypeVar("T")


class ModePolicy(Protocol[T]):
    """Callable returning a mode dynamically based on context."""

    def __call__(self, context: object) -> T:
        ...


RecordModePolicy = ModePolicy[RecordMode]
FallbackModePolicy = ModePolicy[FallbackMode]
