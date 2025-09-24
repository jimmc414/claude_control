"""Exit summary reporting for replay."""

from __future__ import annotations

from typing import Optional


def print_summary(store: Optional[object]) -> None:
    """Print a summary of new and unused tapes."""

    if not store:
        return

    new = sorted(getattr(store, "new", []))
    used = set(getattr(store, "used", []))
    paths = list(getattr(store, "paths", []))

    print("===== SUMMARY (claude_control) =====")
    if new:
        print("New tapes:")
        for path in new:
            print(f"- {path}")
    unused = [p for p in paths if p not in used]
    if unused:
        print("Unused tapes:")
        for path in unused:
            print(f"- {path}")
