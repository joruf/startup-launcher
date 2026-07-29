"""Enable/disable running Startup Launcher automatically at login."""

import sys

from paths import AUTOSTART_DESKTOP_FILENAME, AUTOSTART_DIR, ICON_FILE, MAIN_SCRIPT


def _desktop_entry_content() -> str:
    python_exe = sys.executable or "python3"
    return (
        "[Desktop Entry]\n"
        "Type=Application\n"
        f"Exec={python_exe} {MAIN_SCRIPT} --autostart\n"
        f"Icon={ICON_FILE}\n"
        "X-GNOME-Autostart-enabled=true\n"
        "NoDisplay=false\n"
        "Hidden=false\n"
        "Name=Startup Launcher\n"
        "Comment=Automatically starts the configured programs at login\n"
        "X-GNOME-Autostart-Delay=2\n"
    )


def is_enabled() -> bool:
    """Return whether the autostart entry currently exists."""
    return (AUTOSTART_DIR / AUTOSTART_DESKTOP_FILENAME).is_file()


def enable() -> None:
    """Write the autostart .desktop entry."""
    AUTOSTART_DIR.mkdir(parents=True, exist_ok=True)
    (AUTOSTART_DIR / AUTOSTART_DESKTOP_FILENAME).write_text(_desktop_entry_content(), encoding="utf-8")


def disable() -> None:
    """Remove the autostart .desktop entry, if present."""
    path = AUTOSTART_DIR / AUTOSTART_DESKTOP_FILENAME
    if path.is_file():
        path.unlink()
