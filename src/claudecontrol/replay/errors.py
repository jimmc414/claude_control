"""Probabilistic error injection."""

from __future__ import annotations

import random
from typing import Any


def should_inject_error(config: Any, ctx: object) -> bool:
    """Return True when the configured error rate triggers."""

    if config is None:
        return False
    if callable(config):
        value = float(config(ctx))
    else:
        value = float(config)
    if value <= 0:
        return False
    return random.random() * 100.0 < value
