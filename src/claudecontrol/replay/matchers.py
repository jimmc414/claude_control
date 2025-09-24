"""Matcher definitions for replay."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, Iterable, List, Optional

from .normalize import collapse_ws, scrub, strip_ansi


@dataclass
class MatchingContext:
    """Information about the current session used for matching."""

    program: str
    args: List[str]
    env: Dict[str, str]
    cwd: str
    prompt: Optional[str]


StdinMatcher = Callable[[bytes, bytes, MatchingContext], bool]
CommandMatcher = Callable[[List[str], List[str], MatchingContext], bool]


def default_stdin_matcher(expected: bytes, actual: bytes, ctx: MatchingContext) -> bool:
    """Default stdin matcher that ignores trailing newlines."""

    return expected.rstrip(b"\r\n") == actual.rstrip(b"\r\n")


def default_command_matcher(expected: List[str], actual: List[str], ctx: MatchingContext) -> bool:
    """Default command matcher that normalizes whitespace."""

    norm_expected = [collapse_ws(scrub(strip_ansi(p))) for p in expected]
    norm_actual = [collapse_ws(scrub(strip_ansi(p))) for p in actual]
    return norm_expected == norm_actual


def filter_env(env: Dict[str, str], allow: Optional[Iterable[str]], ignore: Optional[Iterable[str]]) -> Dict[str, str]:
    """Filter environment variables according to allow/ignore lists."""

    if allow:
        env = {k: v for k, v in env.items() if k in allow}
    if ignore:
        env = {k: v for k, v in env.items() if k not in set(ignore)}
    return env
