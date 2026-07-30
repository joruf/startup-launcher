"""Resilient, atomic JSON file persistence shared by models/entries.py,
models/geometry.py, and config/settings.py."""

import json
import os
import tempfile
from pathlib import Path


def load_json(path: Path, default):
    """
    Read JSON from path.

    Returns default if the file doesn't exist or is missing/corrupted (e.g. left
    truncated by a crash mid-write) instead of raising, so a broken data file
    never crashes the whole app on startup.
    """
    if not path.is_file():
        return default
    try:
        with path.open(encoding="utf-8") as handle:
            return json.load(handle)
    except (json.JSONDecodeError, OSError):
        return default


def save_json_atomic(path: Path, data) -> None:
    """
    Write JSON to path atomically.

    Writes to a temp file in the same directory first, then renames it over the
    target (os.replace is atomic on POSIX) - a crash or kill mid-write can never
    leave the target file truncated/corrupted.
    """
    fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        os.replace(tmp_path, path)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
