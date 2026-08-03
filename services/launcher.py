"""Process launching and wmctrl-based window state handling."""

import shlex
import subprocess
import threading
import time
from pathlib import Path

_WMCTRL_STATE = {
    "minimized": "add,hidden",
    "maximized": "add,maximized_vert,maximized_horz",
    "fullscreen": "add,fullscreen",
}

WAIT_TIMEOUT_SECONDS = 20
POLL_INTERVAL_SECONDS = 0.5


def _flatten_command(command):
    """Collapse a (possibly multi-line) command into a single shell-argv line."""
    return " ".join(line.strip() for line in command.splitlines() if line.strip())


def _apply_window_state(entry, log):
    """Poll for the launched window and apply its configured wmctrl state."""
    mode = entry["window_mode"]
    match = entry["match_string"].strip()
    state = _WMCTRL_STATE.get(mode)
    if not state or not match:
        return

    list_cmd = ["wmctrl", "-lx"] if entry["match_mode"] == "class" else ["wmctrl", "-l"]
    deadline = time.monotonic() + WAIT_TIMEOUT_SECONDS

    while time.monotonic() < deadline:
        try:
            result = subprocess.run(list_cmd, capture_output=True, text=True, check=False)
        except OSError as exc:
            log(f"{entry['name']}: wmctrl not available ({exc})")
            return

        if match.lower() in result.stdout.lower():
            apply_cmd = ["wmctrl"]
            if entry["match_mode"] == "class":
                apply_cmd.append("-x")
            apply_cmd += ["-r", match, "-b", state]
            subprocess.run(apply_cmd, check=False)
            log(f"{entry['name']}: window found, applied '{mode}' mode.")
            return

        time.sleep(POLL_INTERVAL_SECONDS)

    log(f"{entry['name']}: window not found (timed out after {WAIT_TIMEOUT_SECONDS}s).")


def launch_entry(entry, log=None, geometry_restore=None):
    """
    Launch a single entry's command and apply its window state.

    :param geometry_restore: optional callable(entry, log) that restores the entry's
        last saved window position/size instead of the normal window-mode handling
        (used for the opt-in "restore positions at startup" feature).
    """
    log = log or (lambda message: None)

    try:
        args = shlex.split(_flatten_command(entry["command"]))
    except ValueError as exc:
        log(f"{entry['name']}: could not parse command ({exc}).")
        return

    if not args:
        log(f"{entry['name']}: no command configured.")
        return

    try:
        subprocess.Popen(args, cwd=str(Path.home()))
    except OSError as exc:
        log(f"{entry['name']}: failed to start ({exc}).")
        return

    log(f"{entry['name']}: started.")

    if geometry_restore is not None:
        threading.Thread(target=geometry_restore, args=(entry, log), daemon=True).start()
    elif entry["window_mode"] != "normal":
        threading.Thread(target=_apply_window_state, args=(entry, log), daemon=True).start()


def _timer_schedule(delay_seconds, callback):
    """Default scheduler for delayed entries: one daemon timer thread each."""
    timer = threading.Timer(delay_seconds, callback)
    timer.daemon = True
    timer.start()


def launch_entries(entries, log=None, geometry_restore=None, schedule=None):
    """
    Launch every enabled entry in the given list (non-blocking, like the old script).

    Entries with a delay_seconds > 0 are launched after that many seconds instead of
    immediately, so a startup sequence can stagger heavy programs.

    :param schedule: optional callable(delay_seconds, callback) used for delayed
        entries; the GUI passes its Tk timer so a delayed launch - and the log line
        it writes - happens on the main thread instead of in a timer thread
    """
    schedule = schedule or _timer_schedule

    for entry in entries:
        if not entry.get("enabled", True):
            continue

        delay = entry.get("delay_seconds", 0)
        if delay > 0:
            schedule(
                delay,
                lambda entry=entry: launch_entry(entry, log=log, geometry_restore=geometry_restore),
            )
        else:
            launch_entry(entry, log=log, geometry_restore=geometry_restore)
