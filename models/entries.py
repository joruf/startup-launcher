"""Entry schema, default seed data, and JSON persistence for launch entries."""

import uuid

from json_store import load_json, save_json_atomic
from paths import ENTRIES_FILE, EXAMPLE_ENTRIES_FILE

WINDOW_MODES = ["normal", "minimized", "maximized", "fullscreen"]
MATCH_MODES = ["class", "title"]

WINDOW_MODE_LABELS = {
    "normal": "Normal",
    "minimized": "Minimized",
    "maximized": "Maximized",
    "fullscreen": "Fullscreen",
}

MATCH_MODE_LABELS = {
    "class": "Window Class (WM_CLASS)",
    "title": "Window Title",
}

MIN_DELAY_SECONDS = 0
MAX_DELAY_SECONDS = 60


def default_entries():
    """
    Return the seed entries for a fresh install.

    Uses entries.example.json if present (the shipped, generic template),
    otherwise starts with an empty list - never hardcodes anyone's personal
    commands/paths here, since this file is committed to source control while
    entries.json itself is git-ignored.
    """
    return load_json(EXAMPLE_ENTRIES_FILE, [])


def new_id():
    """Return a fresh stable identifier for a new entry."""
    return uuid.uuid4().hex


def _ensure_schema(entries):
    """Backfill a stable id and a default delay_seconds on any entry missing them."""
    changed = False
    for entry in entries:
        if not entry.get("id"):
            entry["id"] = new_id()
            changed = True
        if "delay_seconds" not in entry:
            entry["delay_seconds"] = 0
            changed = True
    return changed


def clamp_delay_seconds(value):
    """Clamp a delay value to the supported 0-60 second range."""
    return max(MIN_DELAY_SECONDS, min(MAX_DELAY_SECONDS, value))


def load_entries():
    """Load entries from entries.json, seeding it with defaults if missing or corrupted."""
    entries = load_json(ENTRIES_FILE, None)
    if entries is None:
        entries = default_entries()
        _ensure_schema(entries)
        save_entries(entries)
        return entries

    if _ensure_schema(entries):
        save_entries(entries)
    return entries


def save_entries(entries):
    """Persist entries to entries.json."""
    save_json_atomic(ENTRIES_FILE, entries)


def existing_groups(entries):
    """Return the sorted set of non-empty group names already in use."""
    return sorted({entry.get("group", "").strip() for entry in entries if entry.get("group", "").strip()})
