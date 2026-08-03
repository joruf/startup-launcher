"""
Append-only log of what happened on each start, kept for autostart runs.

An autostart run has no terminal: when it silently does nothing (or dies a few
seconds in, after the first entries were already launched) there is nothing left
to look at afterwards. Every run therefore records its start, what it decided to
launch, and how it ended, so the next login can be checked instead of guessed.
"""

import os
from datetime import datetime

from paths import SESSION_LOG_FILE

MAX_BYTES = 256 * 1024


def _rotate_if_oversized() -> None:
    try:
        if SESSION_LOG_FILE.stat().st_size <= MAX_BYTES:
            return
    except OSError:
        return

    try:
        os.replace(SESSION_LOG_FILE, SESSION_LOG_FILE.with_suffix(".log.1"))
    except OSError:
        pass


def write(message: str) -> None:
    """Append one timestamped line; never raise, logging must not break a start."""
    try:
        SESSION_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        _rotate_if_oversized()
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(SESSION_LOG_FILE, "a", encoding="utf-8") as handle:
            handle.write(f"{stamp} {message}\n")
    except OSError:
        pass
