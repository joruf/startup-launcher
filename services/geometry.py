"""Scan open windows for their position/size and restore saved positions via wmctrl."""

import re
import subprocess
import time

from models import geometry as geometry_model

WAIT_TIMEOUT_SECONDS = 20
POLL_INTERVAL_SECONDS = 0.5

# `wmctrl -lG` output: <id> <desktop> <x> <y> <width> <height> <host> <title...>
# (no -x/WM_CLASS column: that field can itself contain spaces, e.g. "github desktop.GitHub
# Desktop", which breaks whitespace-based column parsing - see _window_class() instead.)
_GEOMETRY_LINE_RE = re.compile(
    r"^(?P<id>0x[0-9a-fA-F]+)\s+-?\d+\s+(?P<x>-?\d+)\s+(?P<y>-?\d+)\s+"
    r"(?P<w>\d+)\s+(?P<h>\d+)\s+\S+\s+(?P<title>.*)$"
)


def _list_windows():
    """Return [{id, x, y, width, height, title}] for every currently open window."""
    try:
        result = subprocess.run(["wmctrl", "-lG"], capture_output=True, text=True, check=False)
    except OSError:
        return []

    windows = []
    for line in result.stdout.splitlines():
        match = _GEOMETRY_LINE_RE.match(line)
        if not match:
            continue
        windows.append(
            {
                "id": match["id"],
                "x": int(match["x"]),
                "y": int(match["y"]),
                "width": int(match["w"]),
                "height": int(match["h"]),
                "title": match["title"],
            }
        )
    return windows


def _window_class(window_id):
    """Return the raw WM_CLASS instance/class text for a window id, via xprop."""
    try:
        result = subprocess.run(
            ["xprop", "-id", window_id, "WM_CLASS"], capture_output=True, text=True, check=False
        )
    except OSError:
        return ""
    return result.stdout


def _find_window(entry, windows):
    """Return the first open window matching the entry's window-match settings, or None."""
    match = entry.get("match_string", "").strip().lower()
    if not match:
        return None

    if entry.get("match_mode") == "class":
        for window in windows:
            if match in _window_class(window["id"]).lower():
                return window
        return None

    for window in windows:
        if match in window["title"].lower():
            return window
    return None


def _clear_and_apply_geometry(entry, window_geometry, log):
    match = entry["match_string"].strip()
    target = ["wmctrl", "-x"] if entry.get("match_mode") == "class" else ["wmctrl"]

    # Un-maximize/un-fullscreen first, otherwise the window manager ignores the
    # explicit geometry we're about to set.
    subprocess.run(
        target + ["-r", match, "-b", "remove,maximized_vert,maximized_horz,fullscreen"], check=False
    )
    move_arg = "0,{x},{y},{width},{height}".format(**window_geometry)
    subprocess.run(target + ["-r", match, "-e", move_arg], check=False)
    log(f"{entry['name']}: position restored.")


def scan_and_store(entries, log=None):
    """Scan all open windows and remember position/size for every trackable entry."""
    log = log or (lambda message: None)
    windows = _list_windows()
    if not windows:
        log("Window scan: no windows found (or wmctrl unavailable).")
        return

    stored = geometry_model.load_geometry()
    found = 0
    for entry in entries:
        if not entry.get("match_string", "").strip():
            continue
        window = _find_window(entry, windows)
        if window is None:
            continue
        stored[entry["id"]] = {
            "x": window["x"],
            "y": window["y"],
            "width": window["width"],
            "height": window["height"],
        }
        found += 1

    geometry_model.save_geometry(stored)
    log(f"Window scan complete: {found} position(s) saved.")


def restore_geometry(entry, log=None):
    """Reposition/resize an already-open window to its last saved geometry."""
    log = log or (lambda message: None)

    saved = geometry_model.load_geometry().get(entry["id"])
    if saved is None:
        log(f"{entry['name']}: no saved position yet - run a scan first.")
        return

    if not entry.get("match_string", "").strip():
        log(f"{entry['name']}: no window match configured, cannot locate its window.")
        return

    window = _find_window(entry, _list_windows())
    if window is None:
        log(f"{entry['name']}: window is not currently open.")
        return

    _clear_and_apply_geometry(entry, saved, log)


def wait_and_restore_geometry(entry, log=None):
    """Poll for the entry's window after launch and apply its saved geometry once found."""
    log = log or (lambda message: None)

    saved = geometry_model.load_geometry().get(entry["id"])
    if saved is None:
        return

    if not entry.get("match_string", "").strip():
        return

    deadline = time.monotonic() + WAIT_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        window = _find_window(entry, _list_windows())
        if window is not None:
            _clear_and_apply_geometry(entry, saved, log)
            return
        time.sleep(POLL_INTERVAL_SECONDS)

    log(f"{entry['name']}: window did not appear in time, could not restore position.")


def forget(entry_ids):
    """Remove stored geometry for the given entry ids (e.g. after an entry is deleted)."""
    stored = geometry_model.load_geometry()
    changed = False
    for entry_id in entry_ids:
        if stored.pop(entry_id, None) is not None:
            changed = True
    if changed:
        geometry_model.save_geometry(stored)
