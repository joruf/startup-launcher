"""Enable/disable running Startup Launcher automatically at login."""

import shutil
import sys

from paths import AUTOSTART_DESKTOP_FILENAME, AUTOSTART_DIR, ICON_FILE, MAIN_SCRIPT, PROJECT_ROOT

# Tells run.py that this start came from the login autostart entry: stay tray-only
# and launch the configured entries (see "Launch entries at login" in Settings).
AUTOSTART_FLAG = "--autostart"

# Cinnamon/GNOME fire autostart entries while the panel - and with it the systray
# area the app lives in - is still coming up. Starting into that race cost the tray
# icon (and, on some logins, the whole process). Waiting a few seconds costs nothing
# at login and makes the run reproducible.
AUTOSTART_DELAY_SECONDS = 10


def _python_executable() -> str:
    """Absolute interpreter path - PATH is not dependable in a login-autostart environment."""
    return sys.executable or shutil.which("python3") or "/usr/bin/python3"


def _desktop_entry_content() -> str:
    return (
        "[Desktop Entry]\n"
        "Type=Application\n"
        f'Exec="{_python_executable()}" "{MAIN_SCRIPT}" {AUTOSTART_FLAG}\n'
        f"Path={PROJECT_ROOT}\n"
        f"Icon={ICON_FILE}\n"
        "Terminal=false\n"
        "StartupNotify=false\n"
        "X-GNOME-Autostart-enabled=true\n"
        "NoDisplay=false\n"
        "Hidden=false\n"
        "Name=Startup Launcher\n"
        "Comment=Automatically starts the configured programs at login\n"
        f"X-GNOME-Autostart-Delay={AUTOSTART_DELAY_SECONDS}\n"
    )


def desktop_file_path():
    """Full path of the login autostart entry this app owns."""
    return AUTOSTART_DIR / AUTOSTART_DESKTOP_FILENAME


def is_enabled() -> bool:
    """Return whether the autostart entry currently exists."""
    return desktop_file_path().is_file()


def enable() -> None:
    """Write the autostart .desktop entry."""
    AUTOSTART_DIR.mkdir(parents=True, exist_ok=True)
    desktop_file_path().write_text(_desktop_entry_content(), encoding="utf-8")


def disable() -> None:
    """Remove the autostart .desktop entry, if present."""
    path = desktop_file_path()
    if path.is_file():
        path.unlink()


def is_outdated() -> bool:
    """
    Return whether an existing autostart entry differs from what we write today.

    :return: False when autostart is off or the entry is already up to date
    """
    path = desktop_file_path()
    if not path.is_file():
        return False

    try:
        return path.read_text(encoding="utf-8") != _desktop_entry_content()
    except OSError:
        return True


def refresh_if_enabled() -> bool:
    """
    Rewrite an outdated autostart entry so a ticked checkbox keeps its promise.

    A .desktop file written by an older version (or edited by a desktop settings
    tool) keeps launching the app the old way - e.g. without the --autostart flag,
    so nothing gets started at login - until the checkbox is toggled off and on
    again. Checking it on every start makes that self-healing.

    :return: True when the entry was rewritten
    """
    if not is_outdated():
        return False

    enable()
    return True
