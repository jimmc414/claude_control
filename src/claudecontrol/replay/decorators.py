"""Decorator protocol definitions."""

from __future__ import annotations

from typing import Callable

from .matchers import MatchingContext

InputDecorator = Callable[[MatchingContext, bytes], bytes]
OutputDecorator = Callable[[MatchingContext, bytes], bytes]
TapeDecorator = Callable[[MatchingContext, dict], dict]


def compose_decorators(*decorators: InputDecorator) -> InputDecorator:
    """Compose decorators left-to-right."""

    def _composed(ctx: MatchingContext, data: bytes) -> bytes:
        result = data
        for decorator in decorators:
            if decorator:
                result = decorator(ctx, result)
        return result

    return _composed
