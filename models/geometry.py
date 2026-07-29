"""Persistence for the last-seen window position/size per entry."""

import json

from paths import GEOMETRY_FILE


def load_geometry():
    """Return {entry_id: {x, y, width, height}} for every entry with a saved position."""
    if not GEOMETRY_FILE.is_file():
        return {}
    with GEOMETRY_FILE.open(encoding="utf-8") as handle:
        return json.load(handle)


def save_geometry(data):
    """Persist the {entry_id: {x, y, width, height}} mapping."""
    with GEOMETRY_FILE.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
