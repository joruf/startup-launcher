"""Persistence for app-wide settings (window-position scanning, startup restore)."""

from json_store import load_json, save_json_atomic
from paths import SETTINGS_FILE

DEFAULTS = {
    "scan_enabled": True,
    "scan_interval_minutes": 10,
    # Whether an autostart run (run.py --autostart) launches the enabled entries.
    # On by default: that is the whole point of the login autostart entry. Turn it
    # off to have the launcher itself start into the tray without touching anything.
    "launch_at_login": True,
    # Off by default: only enable once saved positions look right when restored manually.
    "restore_on_startup": False,
    # Set True only by a graceful quit (File/tray > Quit); cleared at the start of every
    # session. Lets restore-on-startup skip a session that ended in a crash, since the
    # last-saved positions may not reflect where windows really were.
    "clean_shutdown": False,
}


def load_settings():
    """Return current settings, merged over the defaults for any missing/corrupted keys."""
    data = load_json(SETTINGS_FILE, {})
    merged = dict(DEFAULTS)
    merged.update(data)
    return merged


def save_settings(data):
    """Persist settings to settings.json."""
    save_json_atomic(SETTINGS_FILE, data)


def mark_session_started():
    """Clear the clean-shutdown flag at the start of a session (call once at startup)."""
    current = load_settings()
    was_clean = current.get("clean_shutdown", False)
    current["clean_shutdown"] = False
    save_settings(current)
    return was_clean


def mark_clean_shutdown():
    """Mark the current session as having exited gracefully (call on a real quit)."""
    current = load_settings()
    current["clean_shutdown"] = True
    save_settings(current)
