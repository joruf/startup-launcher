"""Persistence for the last-seen window position/size per entry."""

from json_store import load_json, save_json_atomic
from paths import GEOMETRY_FILE


def load_geometry():
    """Return {entry_id: {x, y, width, height}} for every entry with a saved position."""
    return load_json(GEOMETRY_FILE, {})


def save_geometry(data):
    """Persist the {entry_id: {x, y, width, height}} mapping."""
    save_json_atomic(GEOMETRY_FILE, data)
