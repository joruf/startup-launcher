"""Shared filesystem paths for Startup Launcher."""

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
RESOURCES_DIR = PROJECT_ROOT / "resources"

STATE_DIR = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state"))
RUNTIME_DIR = Path(os.environ.get("XDG_RUNTIME_DIR", STATE_DIR))
LOCK_DIR = RUNTIME_DIR / "startup-launcher"

# Outlives the login session on purpose: an autostart run that fails has to stay
# readable after the next reboot.
SESSION_LOG_FILE = STATE_DIR / "startup-launcher" / "session.log"

ENTRIES_FILE = PROJECT_ROOT / "entries.json"
EXAMPLE_ENTRIES_FILE = PROJECT_ROOT / "entries.example.json"
GEOMETRY_FILE = PROJECT_ROOT / "window_geometry.json"
SETTINGS_FILE = PROJECT_ROOT / "settings.json"
MAIN_SCRIPT = PROJECT_ROOT / "run.py"
ICON_FILE = RESOURCES_DIR / "startup-launcher.png"
DESKTOP_TEMPLATE = RESOURCES_DIR / "startup-launcher.desktop"

AUTOSTART_DIR = Path.home() / ".config" / "autostart"
AUTOSTART_DESKTOP_FILENAME = "Startup Launcher.desktop"
