"""Persistence for app-wide settings (window-position scanning, startup restore)."""

import json

from paths import SETTINGS_FILE

DEFAULTS = {
    "scan_enabled": True,
    "scan_interval_minutes": 10,
    # Off by default: only enable once saved positions look right when restored manually.
    "restore_on_startup": False,
}


def load_settings():
    """Return current settings, merged over the defaults for any missing keys."""
    if not SETTINGS_FILE.is_file():
        return dict(DEFAULTS)

    with SETTINGS_FILE.open(encoding="utf-8") as handle:
        data = json.load(handle)

    merged = dict(DEFAULTS)
    merged.update(data)
    return merged


def save_settings(data):
    """Persist settings to settings.json."""
    with SETTINGS_FILE.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
