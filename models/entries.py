"""Entry schema, default seed data, and JSON persistence for launch entries."""

import json
import uuid

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


def default_entries():
    """
    Return the seed entries for a fresh install.

    Uses entries.example.json if present (the shipped, generic template),
    otherwise starts with an empty list - never hardcodes anyone's personal
    commands/paths here, since this file is committed to source control while
    entries.json itself is git-ignored.
    """
    if EXAMPLE_ENTRIES_FILE.is_file():
        with EXAMPLE_ENTRIES_FILE.open(encoding="utf-8") as handle:
            return json.load(handle)
    return []


def new_id():
    """Return a fresh stable identifier for a new entry."""
    return uuid.uuid4().hex


def _ensure_ids(entries):
    """Backfill a stable id on any entry that doesn't have one yet."""
    changed = False
    for entry in entries:
        if not entry.get("id"):
            entry["id"] = new_id()
            changed = True
    return changed


def load_entries():
    """Load entries from entries.json, seeding it with defaults on first run."""
    if not ENTRIES_FILE.is_file():
        entries = default_entries()
        _ensure_ids(entries)
        save_entries(entries)
        return entries

    with ENTRIES_FILE.open(encoding="utf-8") as handle:
        entries = json.load(handle)

    if _ensure_ids(entries):
        save_entries(entries)
    return entries


def save_entries(entries):
    """Persist entries to entries.json."""
    with ENTRIES_FILE.open("w", encoding="utf-8") as handle:
        json.dump(entries, handle, indent=2, ensure_ascii=False)
        handle.write("\n")


def existing_groups(entries):
    """Return the sorted set of non-empty group names already in use."""
    return sorted({entry.get("group", "").strip() for entry in entries if entry.get("group", "").strip()})
