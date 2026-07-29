# Startup Launcher

GUI to manage the programs started at login - replaces a plain bash startup
script with per-entry window placement, grouping, and position memory.

## Usage

```bash
python3 run.py
```

`entries.json`, `window_geometry.json`, and `settings.json` hold your personal
data (your own commands/paths, window positions, preferences) and are
git-ignored. On first run, if `entries.json` doesn't exist yet, copy the
template to get started:

```bash
cp entries.example.json entries.json
```

(If you skip this, the app creates `entries.json` for you on first run,
seeded from `entries.example.json` if present, or empty otherwise - see
"Data lives in..." below.)

- **New / Edit / Delete** — manage entries. Each entry has a command, a
  window mode (Normal, Minimized, Maximized, Fullscreen), and — for anything
  other than Normal — a window match (window class `WM_CLASS` or window
  title) plus a search term, used by `wmctrl` to find the window and apply
  the desired state.
- **Command** is a multi-line text field — long invocations with many
  paths/arguments (e.g. the Nemo entry) can be spread across multiple lines
  for readability; they are joined back into a single command line on save.
- **Enabled** is a checkbox right in the table (☑/☐), not a field in the
  dialog. Each entry has its own checkbox; each group also has one that
  reflects and controls all of its members at once: checking/unchecking a
  group's box checks/unchecks every entry in that group. A group shows ☒
  when its members are mixed (some enabled, some not).
- **Group** — entries sharing the same group name (e.g. "VSCode") are shown
  nested under one node in the tree. Double-click/"Restart" on the group
  node starts every entry in the group; double-click on a single entry
  starts only that one. "Delete" on the group node removes the whole group
  (with confirmation); "Edit"/"Move Up"/"Move Down" only apply to individual
  entries.
- **Move Up / Move Down** — change the order of entries.
- **Double-click** on an entry or a group (or "Restart") runs that
  command/group again, regardless of its enabled state.
- **Start All** runs every enabled entry (like the old bash script).
- Checkbox at the top: writes/removes an autostart entry at
  `~/.config/autostart/Startup Launcher.desktop`. When run via autostart,
  the program is called with `--autostart` and automatically starts all
  enabled entries shortly after launching.

## Window Positions

Any entry with a window match (window class or title - not just the ones
using Minimized/Maximized/Fullscreen; a Normal entry can have one too, purely
for tracking) can have its position/size remembered and restored:

- **Window Positions > Scan Now** (menu) scans every currently open window
  right away and stores the position/size of each entry that has a match.
  A scan also runs automatically in the background on a timer.
- The rightmost **Position** column in the table shows the last saved
  `x,y  WxH` for any entry that has one, and stays blank otherwise.
- **Restore Position** (button) moves/resizes the currently open window for
  the selected entry - or, for a group, every member of that group - back to
  its last saved position/size. The window has to already be open; this
  doesn't launch anything.
- **Window Positions > Settings...** configures the scan interval and
  whether scanning runs at all, plus one more switch: "Restore saved window
  positions automatically at startup". That one is **off by default** - turn
  it on only once "Restore Position" has shown you the saved positions look
  right. When it's on and the program is launched via autostart, every
  entry with a saved position gets moved there right after it starts,
  instead of just Normal/Minimized/Maximized/Fullscreen - the goal being the
  same window layout after login as before shutdown. Manually clicking
  "Start All" never uses this - only the real autostart run does.
- Saved positions live in `window_geometry.json`, keyed by each entry's
  internal id (not its name/position in the list, so renaming or reordering
  entries doesn't lose their saved geometry). Deleting an entry or group
  also forgets its saved position.

## System Tray

The program always starts tray-only (GTK3 `Gtk.StatusIcon`, the same
approach as `devserver-commander`) — no window is shown at launch. Clicking
the tray icon, or "Show Startup Launcher" in its context menu, opens the
window; closing the window (X button, or File > "Minimize to Tray") just
hides it again instead of quitting. Quitting goes through File > "Quit" or
"Quit" in the tray menu. If GTK3 (`python3-gi` + `gir1.2-gtk-3.0`) isn't
installed, the window stays visible as a fallback.

## Look & Feel

The ttk theme (`ui/style.py`) is copied 1:1 from `devserver-commander`
(same zinc/neutral-gray palette, buttons, treeview), so both tools look
alike.

Data lives in `entries.json` next to the script (git-ignored - it's your
personal list). On first run it's created automatically, seeded from
`entries.example.json` if present, otherwise empty. Window positions live in
`window_geometry.json`; scan/restore settings live in `settings.json` - both
next to `entries.json`, also git-ignored, created on first use.

## Project Layout

Modeled after `devserver-commander`:

```
startup-launcher/
├── run.py                  # thin entry point
├── paths.py                # shared path constants
├── entries.json            # your data (git-ignored)
├── entries.example.json    # generic template, committed - copy to entries.json
├── window_geometry.json    # last-seen position/size per entry (git-ignored)
├── settings.json           # scan interval/enabled, restore-on-startup (git-ignored)
├── models/entries.py       # schema, default seed, JSON persistence
├── models/geometry.py      # window_geometry.json persistence
├── services/launcher.py    # process start + wmctrl window state
├── services/geometry.py    # scan/restore window position via wmctrl
├── config/autostart.py     # manage the autostart desktop entry
├── config/settings.py      # settings.json persistence
├── ui/main_window.py       # main window (StartupLauncherApp)
├── ui/entry_dialog.py      # New/Edit dialog
├── ui/settings_dialog.py    # Settings dialog
├── ui/style.py              # ttk theme (copied from devserver-commander)
├── ui/tray.py                # GTK3 system tray
├── ui/window_icon.py         # window/taskbar icon
└── resources/                # icon + .desktop template
```

## Note: old autostart icon

`~/.config/autostart/Start Config.desktop` still starts
`startup-config.sh` directly. If Startup Launcher's autostart checkbox is
enabled, the old entry should be disabled/removed, otherwise every program
would start twice at login.
