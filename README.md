# Startup Launcher

A GUI to manage the programs started at login - replaces a plain bash startup
script with per-entry window placement, grouping, delayed starts, and window
position memory.

📖 See **[MANUAL.md](MANUAL.md)** for the full user guide.

## Features

- Add/edit/delete/reorder login entries; group them (e.g. all VSCode
  windows) and start a whole group with one click
- Per-entry window mode (Normal, Minimized, Maximized, Fullscreen) applied
  via `wmctrl`, plus a per-entry startup delay (0-60s) to stagger heavy
  programs
- Click-to-edit table: Name, Command, Delay, and window XY/Size can all be
  edited directly in the table, no dialog needed
- Window position memory: scan open windows, save their position/size, and
  restore it per entry or group - with an opt-in "restore automatically at
  login" that only kicks in after a clean shutdown
- Enable/disable via checkboxes right in the table, with group-level cascade
- Sortable columns, live-reload if `entries.json` changes on disk
- Runs tray-only (GTK3), autostart toggle in the File/tray menu, and only
  one instance can ever run at a time

## Requirements

- Linux with a window manager exposing `wmctrl` (Cinnamon/GNOME/XFCE/etc.)
- `wmctrl` and `xprop` (window matching, scanning, and restoring positions)
- Python 3.9+ with `tkinter` (`python3-tk` on Debian/Ubuntu/Mint)
- GTK3 + PyGObject (`python3-gi`, `gir1.2-gtk-3.0`) for the system tray icon
  - optional: without it, the app falls back to a normal visible window
    when started manually (autostart launches always stay hidden either way)

## Usage

```bash
git clone https://github.com/joruf/startup-launcher.git
cd startup-launcher
chmod +x run.py
./run.py
```

`entries.json`, `window_geometry.json`, and `settings.json` hold your
personal data (your own commands/paths, window positions, preferences) and
are git-ignored - they're created automatically on first run, seeded from
`entries.example.json` if present, or empty otherwise. To start from the
bundled example entries instead of empty:

```bash
cp entries.example.json entries.json
```

## Entries & the Table

- **New / Edit / Delete** — manage entries. Each entry has a command, a
  window mode (Normal, Minimized, Maximized, Fullscreen), a delay in seconds
  (0-60, default 0 - how long after the app/login starts before this entry
  launches, so a startup sequence can stagger heavy programs), and — for
  anything other than Normal — a window match (window class `WM_CLASS` or
  window title) plus a search term, used by `wmctrl` to find the window and
  apply the desired state.
- **Command** is a multi-line text field — long invocations with many
  paths/arguments (e.g. the Nemo entry) can be spread across multiple lines
  for readability. That formatting is kept as-is across edits; it's only
  flattened into a single shell line at the moment the command actually runs.
- Double-click **Name**, **Delay**, **Command**, **XY**, or **Size** in the
  table to edit that cell in place (Enter/click away to save, Escape to
  cancel) - no need to open "Edit..." for a quick tweak. A single click just
  selects the row, like anywhere else in the table. XY takes `x,y` (e.g.
  `100,50`); Size takes `widthxheight` (e.g. `1920x1080`) - editing either one
  here writes straight into `window_geometry.json`, the same store Scan/
  Restore Position use, so you can seed a position by hand without scanning
  first.
- Click any **column header** to sort the whole table by that column;
  click again to reverse the order. The sort order is saved like any other
  reorder.
- **Enabled** is a checkbox right in the table (☑/☐), not a field in the
  dialog. Each entry has its own checkbox; each group also has one that
  reflects and controls all of its members at once: checking/unchecking a
  group's box checks/unchecks every entry in that group. A group shows ☒
  when its members are mixed (some enabled, some not).
- The **Launch** column's ▶ button opens the entry right from the table (a
  single click) - or, for a group row, every member of that group - the same
  action as the toolbar's "Restart" button. This is the only way to launch
  from the table; double-click is reserved for editing (see above).
- **Group** — entries sharing the same group name (e.g. "VSCode") are shown
  nested under one node in the tree. Clicking ▶ (or "Restart") on the group
  node starts every entry in the group; clicking it on a single entry
  starts only that one. "Delete" on the group node removes the whole group
  (with confirmation); "Edit"/"Move Up"/"Move Down" only apply to individual
  entries.
- **Move Up / Move Down** — change the order of entries.
- **Start All** runs every enabled entry (like the old bash script),
  respecting each entry's delay.
- **entries.json is watched** - if you (or some other tool) edit it on disk
  while the app is running, the table picks up the change automatically
  within a couple of seconds.
- File > "Run Automatically at Startup" (also mirrored as a checkable item
  in the tray icon's right-click menu) writes/removes an autostart entry at
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
- The **XY** and **Size** columns in the table show the last saved position
  (`x,y`) and size (`widthxheight`) for any entry that has one, and stay
  blank otherwise. Both are directly editable in place (see above).
- **Restore Position** (button) moves/resizes the currently open window for
  the selected entry - or, for a group, every member of that group - back to
  its last saved position/size. The window has to already be open; this
  doesn't launch anything.
- **Window Positions > Settings...** configures the scan interval and
  whether scanning runs at all, plus one more switch: "Restore saved window
  positions automatically at startup". That one is **off by default** - turn
  it on only once "Restore Position" has shown you the saved positions look
  right. When it's on, the program is launched via autostart, *and the
  previous session exited cleanly* (see below), every entry with a saved
  position gets moved there right after it starts, instead of just Normal/
  Minimized/Maximized/Fullscreen - the goal being the same window layout
  after login as before shutdown. Manually clicking "Start All" never uses
  this - only the real autostart run does.
- **Exiting cleanly saves your layout.** Quitting via File/tray > "Quit"
  triggers one final scan of all open windows right before the app closes,
  so the saved positions reflect exactly how the desktop looked at shutdown.
  This also flips a "clean shutdown" flag in `settings.json`. If a *future*
  session doesn't reach that quit path (crash, force-kill, power loss), the
  flag stays unset - and "restore at startup" is skipped once on the next
  launch, since the last-saved positions might not be trustworthy. It's
  cleared again at the very start of every session either way, so autostart
  restore always requires the *immediately preceding* session to have
  exited cleanly.
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
installed, the window stays visible as a fallback for a manual launch - an
autostart launch always stays hidden regardless.

## Single Instance

Only one Startup Launcher can run at a time - the same `fcntl.flock` +
Unix-socket approach `devserver-commander` already uses
(`services/single_instance.py`, `services/instance_ipc.py`). A second launch
attempt (e.g. accidentally double-clicking the desktop icon while it's
already running in the tray) doesn't open a duplicate: it asks the running
instance to show itself (so a "hidden in the tray" instance actually becomes
visible) and tells you it's already running, instead of proceeding. A second
`--autostart` launch (e.g. autostart firing twice) is blocked the same way,
just silently, with no dialog. The lock is an OS-level file lock tied to the
process, so it's automatically released even if the app crashes or gets
killed - never something you'd need to clean up by hand.

## Look & Feel

The ttk theme (`ui/style.py`) is copied 1:1 from `devserver-commander`
(same zinc/neutral-gray palette, buttons, treeview), so both tools look
alike.

Data lives in `entries.json` next to the script (git-ignored - it's your
personal list). On first run it's created automatically, seeded from
`entries.example.json` if present, otherwise empty. Window positions live in
`window_geometry.json`; scan/restore/clean-shutdown settings live in
`settings.json` - both next to `entries.json`, also git-ignored, created on
first use. All three are read/written through `json_store.py`, which makes
writes atomic (temp file + rename) and reads resilient (a missing/corrupted
file falls back to a safe default instead of crashing the app).

The button bar (`ui/wrap_bar.py`) wraps onto extra rows if the window is too
narrow to fit every button on one line, growing the window automatically
rather than letting a button run off-screen.

## Project Layout

Modeled after `devserver-commander`:

```
startup-launcher/
├── run.py                    # thin entry point
├── paths.py                  # shared path constants
├── json_store.py             # atomic writes + resilient reads for the JSON files below
├── entries.json               # your data (git-ignored)
├── entries.example.json       # generic template, committed - copy to entries.json
├── window_geometry.json       # last-seen position/size per entry (git-ignored)
├── settings.json              # scan/restore/clean-shutdown settings (git-ignored)
├── models/entries.py          # schema, default seed, JSON persistence
├── models/geometry.py         # window_geometry.json persistence
├── services/launcher.py       # process start + wmctrl window state + per-entry delay
├── services/geometry.py       # scan/restore window position via wmctrl
├── services/single_instance.py # single-instance lock (fcntl.flock)
├── services/instance_ipc.py   # Unix-socket "show yourself" IPC for the lock above
├── config/autostart.py        # manage the autostart desktop entry
├── config/settings.py         # settings.json persistence + clean-shutdown flag
├── ui/main_window.py          # main window (StartupLauncherApp)
├── ui/entry_dialog.py         # New/Edit dialog
├── ui/settings_dialog.py      # Settings dialog
├── ui/wrap_bar.py             # self-wrapping button bar
├── ui/style.py                # ttk theme (copied from devserver-commander)
├── ui/tray.py                 # GTK3 system tray
├── ui/window_icon.py          # window/taskbar icon
└── resources/                  # icon + .desktop template
```

## Testing

```bash
python3 -m unittest tests.test_cross_platform_contract -v
python3 -m unittest discover -s tests -v
```

CI runs these checks on Ubuntu 22.04/24.04 (Python 3.11 and 3.12) on every push and
pull request. **Windows is not supported** (requires `wmctrl` / Linux window management).

### Multi-OS matrix (local Linux host)

```bash
~/os-test-matrix/bin/test-project /path/to/startup-launcher
~/os-test-matrix/bin/test-project "$PWD" --only ubuntu-2404
```

On-demand Linux runners: [`OS Matrix`](.github/workflows/os-matrix.yml).
Results: `~/os-test-matrix/results/`.

## Note: old autostart icon

`~/.config/autostart/Start Config.desktop` still starts
`startup-config.sh` directly. If Startup Launcher's autostart checkbox is
enabled, the old entry should be disabled/removed, otherwise every program
would start twice at login.
