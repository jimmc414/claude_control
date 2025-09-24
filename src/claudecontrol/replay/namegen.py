"""Default tape naming strategy."""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass
class TapeNameGenerator:
    """Simple content-aware tape name generator."""

    root: Path

    def __call__(self, ctx: object) -> Path:
        program = getattr(ctx, "command", "session")
        preview = getattr(ctx, "_last_input_preview", "")
        key = f"{program}|{preview}|{int(time.time() * 1000)}"
        digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:8]
        safe_program = Path(program.split()[0]).name or "session"
        return self.root / safe_program / f"unnamed-{digest}.json5"
