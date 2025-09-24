"""Latency policies for replay."""

from __future__ import annotations

import random
from typing import Any


def resolve_latency(config: Any, ctx: object) -> int:
    """Resolve a latency configuration to milliseconds."""

    if callable(config):
        return int(config(ctx))
    if isinstance(config, (list, tuple)) and len(config) == 2:
        low, high = config
        return int(random.randint(int(low), int(high)))
    if config is None:
        return 0
    return int(config)
