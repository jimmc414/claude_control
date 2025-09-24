"""Dataclasses describing the replay tape format."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class Chunk:
    """One chunk of program output."""

    delay_ms: int
    data_b64: str
    is_utf8: bool = True


@dataclass
class IOInput:
    """Recorded user input."""

    kind: str  # "line" | "raw"
    data_text: Optional[str] = None
    data_b64: Optional[str] = None


@dataclass
class IOOutput:
    """Recorded program output."""

    chunks: List[Chunk] = field(default_factory=list)


@dataclass
class Exchange:
    """One interaction from prompt to next prompt/exit."""

    pre: Dict[str, Any]
    input: IOInput
    output: IOOutput
    exit: Optional[Dict[str, Any]] = None
    dur_ms: Optional[int] = None
    annotations: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TapeMeta:
    """Metadata describing the session the tape was captured from."""

    created_at: str
    program: str
    args: List[str]
    env: Dict[str, str]
    cwd: str
    pty: Optional[Dict[str, int]] = None
    tag: Optional[str] = None
    latency: Any = 0
    error_rate: Any = 0
    seed: Optional[int] = None


@dataclass
class Tape:
    """Complete tape description."""

    meta: TapeMeta
    session: Dict[str, Any]
    exchanges: List[Exchange] = field(default_factory=list)
