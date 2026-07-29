"""Shared filesystem paths for Startup Launcher."""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
RESOURCES_DIR = PROJECT_ROOT / "resources"

ENTRIES_FILE = PROJECT_ROOT / "entries.json"
EXAMPLE_ENTRIES_FILE = PROJECT_ROOT / "entries.example.json"
GEOMETRY_FILE = PROJECT_ROOT / "window_geometry.json"
SETTINGS_FILE = PROJECT_ROOT / "settings.json"
MAIN_SCRIPT = PROJECT_ROOT / "run.py"
ICON_FILE = RESOURCES_DIR / "startup-launcher.png"
DESKTOP_TEMPLATE = RESOURCES_DIR / "startup-launcher.desktop"

AUTOSTART_DIR = Path.home() / ".config" / "autostart"
AUTOSTART_DESKTOP_FILENAME = "Startup Launcher.desktop"
