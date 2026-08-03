# Startup Launcher — User Manual

A practical guide to using the app day to day. For installation, requirements,
and architecture, see [README.md](README.md) and the
[Technische Dokumentation](TECHNISCHE-DOKUMENTATION.md) (German).

## 1. First Launch

```bash
./run.py
```

Startup Launcher never shows a window when it starts - it only puts an icon
in your system tray. **Click the tray icon** to open the main window.

If you've never used the app before, `entries.json` doesn't exist yet, so the
table starts out either empty or pre-filled from `entries.example.json`
(whichever is present) - see [README.md](README.md#usage) for how to seed it.

## 2. The Main Window

**Toolbar** (top): New, Edit, Delete, Move Up, Move Down, Restart, Restore
Position, Start All. All except New and Start All only work once you've
selected a row, and gray themselves out otherwise. If the window gets too
narrow to fit every button on one line, they wrap onto a second row and the
window grows to make room - nothing ever gets clipped off-screen.

**Table columns**, left to right:

| Column | What it shows | How to change it |
|---|---|---|
| Name | The entry's label | Double-click to edit in place |
| Launch (▶) | — | Single click to launch this entry (or every entry in a group row) |
| Enabled | ☑ / ☐ / ☒ (mixed, group only) | Single click to toggle; toggling a group toggles all its members |
| Window Mode | Normal / Minimized / Maximized / Fullscreen | Via "Edit..." only |
| Delay (s) | Seconds to wait after startup before launching | Double-click to edit in place |
| Command | The shell command that runs | Double-click to edit in place (quick single-line edit; use "Edit..." for the full multi-line view) |
| XY | Last saved window position | Double-click to edit in place (`x,y`, e.g. `100,50`) |
| Size | Last saved window size | Double-click to edit in place (`widthxheight`, e.g. `1920x1080`) |

A single click anywhere else in a row just selects it, the same as in any
table.

Click any **column header** to sort by that column; click again to reverse
the order.

**Right-click** any row for a context menu with the same actions as the
toolbar (Restart, Restore Position, Edit..., Delete..., Move Up, Move Down).

## 3. Adding and Organizing Entries

1. Click **New**, fill in a name and a command, pick a window mode.
2. If you pick Minimized/Maximized/Fullscreen, you must also give a
   **window match** — either the window's class (`WM_CLASS`, robust for
   single-instance apps like a file manager) or its title (needed when
   several windows share a class, e.g. multiple VS Code windows — match on
   part of the folder name shown in the title). This search term is also
   what Scan/Restore Position use to find the window later.
3. Give entries that belong together the same **Group** name (e.g.
   `VSCode`). They'll be shown nested under one row in the table, and you
   can enable, launch, or restore the position of the whole group at once
   by acting on that group row instead of each entry individually.
4. Set a **Delay** if you want this entry to wait a few seconds after the
   others before launching — handy for staggering heavy programs so they
   don't all fight for CPU/disk at once during login.

Reorder entries with **Move Up/Move Down**, or by clicking a column header
to sort the whole table (the sort order is saved, just like a manual
reorder).

## 4. Launching Programs

- **▶ in the Launch column** — launches that one entry, or every entry in a
  group if clicked on a group row. This is the way to start something from
  the table.
- **Restart** (toolbar/context menu) — same thing, for whatever row is
  currently selected.
- **Start All** — launches every *enabled* entry, respecting each one's
  delay. This is what also runs automatically at login if autostart is on.

None of these check whether the program is already running — clicking
Launch twice starts it twice.

## 5. Remembering and Restoring Window Positions

1. Arrange your windows the way you like them.
2. **Window Positions > Scan Now** — takes a snapshot of every open window
   that has a search term configured (see step 2 above) and remembers its
   position and size. This also happens automatically in the background —
   configure how often in **Window Positions > Settings...**.
3. Later, select an entry (or a group) and click **Restore Position** to
   move its already-open window back to the saved spot. This only works on
   windows that are currently open — it doesn't launch anything.
4. You can also type a position/size directly into the **XY**/**Size**
   columns without ever running a scan, if you already know the coordinates
   you want.

### Restoring automatically at login

Once you're happy with how Restore Position behaves manually, you can turn
on **Window Positions > Settings... > "Restore saved window positions
automatically at startup"**. It's off by default on purpose. When it's on,
every autostart launch will:

- Save the current layout of all your windows the moment you cleanly quit
  the app (File/tray > Quit) — so what gets restored next time is exactly
  how things looked when you last shut down.
- Skip the restore *once* if the previous session ended in a crash or a
  forced kill rather than a clean quit, since the saved positions might not
  be trustworthy in that case. Everything goes back to normal (Normal/
  Minimized/Maximized/Fullscreen handling) for that one launch.

## 6. Running Automatically at Login

Two switches work together here:

1. **File > "Run Automatically at Startup"** (also a checkbox in the tray
   icon's right-click menu — both control the same setting) starts *the
   launcher itself* at login. It writes or removes a `.desktop` file in
   `~/.config/autostart/`.
2. **Window Positions > Settings... > "Launch the enabled entries
   automatically at login"** decides whether that login run then *starts
   your programs* (like Start All) or just waits in the tray. On by default.

So switch 1 off means nothing happens at login at all; switch 1 on with
switch 2 off gives you the tray icon and nothing else.

The login run deliberately stays invisible — you get a tray icon, not a
window. Started by hand, the window opens normally.

The autostart entry is re-checked on every start and rewritten when it is out
of date (written by an older version, or edited by a desktop settings tool),
so a ticked checkbox keeps doing what it promises across updates.

Your programs start about 10 seconds into the login: the entry asks the
desktop to wait that long so the panel and its tray area are up first.
Per-entry delays are counted from there.

### Checking what happened at the last login

**Help > Startup Log...** shows the last few starts: when the app started,
whether it came from autostart, how many entries it launched, and whether it
exited normally or died. A login run has no terminal to print to, so this
file (`~/.local/state/startup-launcher/session.log`) is where to look when
something didn't come up.

If you were previously using an old bash script directly via autostart,
disable that old entry once Startup Launcher's autostart is on, or your
programs will start twice — see the note at the bottom of
[README.md](README.md).

## 7. Only One Copy Runs at a Time

If you try to launch the app while it's already running (in the tray or
open), it won't start a second copy. Instead, the already-running instance
is brought to the front, and you'll see an "Already Running" message. If
autostart happens to trigger the app twice, the second attempt is blocked
silently, with no message.

## 8. Troubleshooting

- **No tray icon appears / the window just stays open when launched
  manually.** GTK3 + PyGObject (`python3-gi`, `gir1.2-gtk-3.0`) probably
  aren't installed — the app falls back to a normal window in that case for
  a manual launch (an autostart launch stays hidden regardless, see
  README). Install those packages to get the tray icon back.
- **"Restore Position" says the window isn't open.** The target program
  has to already be running — Restore Position repositions, it doesn't
  launch.
- **A field shows blank when clicking to edit it.** Shouldn't happen; if it
  does, click away and try again, and consider it a bug worth reporting.
- **`entries.json` changed but the table looks stale.** It's checked every
  couple of seconds — give it a moment, or reopen the window.
