"""Main application window for Startup Launcher."""

import os
import sys
import threading
import tkinter as tk
import traceback
from tkinter import messagebox, ttk

from config import autostart
from config import settings as settings_store
from models import entries as entry_model
from models import geometry as geometry_model
from paths import ENTRIES_FILE, ICON_FILE, SESSION_LOG_FILE
from services import geometry as geometry_service
from services import launcher
from services import session_log
from services.instance_ipc import InstanceControlServer
from services.single_instance import enforce_single_instance
from ui.entry_dialog import EntryDialog
from ui.settings_dialog import SettingsDialog
from ui.style import MUTED_FG, PANEL_BG, SELECTION_COLOR, TEXT_FG, configure_ui_style
from ui.tooltip import Tooltip
from ui.tray import TrayIcon
from ui.wrap_bar import WrapButtonBar
from ui.window_icon import apply_window_icon

CHECKED = "☑"  # ☑
UNCHECKED = "☐"  # ☐
PARTIAL = "☒"  # ☒ (some, but not all, group members enabled)
LAUNCH_GLYPH = "▶"

# ttk.Treeview only lets #0 show a per-item image; a data column can't render
# anything bigger than the rest of the row's text. So the checkbox and the
# per-row launch button are drawn with a real Label placed on top of that cell
# instead - the only way to make them bigger while every other column keeps
# its normal size, and the only way to give a data column a clickable "button"
# at all.
CHECKBOX_FONT = ("TkDefaultFont", 15)

# Slightly smaller than the row's default font so the inline Entry/Spinbox
# overlays (see _begin_inline_edit) don't clip descenders against the fixed
# row height.
INLINE_EDIT_FONT = ("TkDefaultFont", 9)

ENTRIES_POLL_INTERVAL_MS = 2000

# Let the window/tray finish coming up before the first programs are spawned; the
# login itself is already staggered by the .desktop entry's autostart delay.
AUTOSTART_LAUNCH_DELAY_MS = 300

# Enough to cover the last few starts without turning the dialog into a wall of text.
SESSION_LOG_TAIL_LINES = 20

# Columns after the tree's own #0 (Name) column. "launch" isn't sortable (no
# underlying data to sort by), so it's excluded from the header-click-to-sort
# wiring in __init__.
COLUMNS = ("launch", "enabled", "mode", "delay", "command", "xy", "size")
COLUMN_LABELS = {
    "#0": "Name",
    "launch": "Launch",
    "enabled": "Enabled",
    "mode": "Window Mode",
    "delay": "Delay (s)",
    "command": "Command",
    "xy": "XY",
    "size": "Size",
}
# Treeview column ids ("#0", "#1", ...) that support single-click inline editing,
# mapped to the entry/geometry field they edit. "launch" (button) and "enabled"
# (checkbox) are overlay widgets, not text; "mode" is a fixed set of options
# edited via the New/Edit dialog. All three are deliberately excluded here.
EDITABLE_FIELD_BY_TREECOL = {
    "#0": "name",
    "#4": "delay",
    "#5": "command",
    "#6": "xy",
    "#7": "size",
}


def _format_xy(saved):
    return f"{saved['x']},{saved['y']}" if saved else ""


def _format_size(saved):
    return f"{saved['width']}x{saved['height']}" if saved else ""


def _flatten_command(command):
    """Collapse a (possibly multi-line) command into a single line for quick display/edit."""
    return " ".join(line.strip() for line in command.splitlines() if line.strip())


class StartupLauncherApp:
    """Main application window."""

    def __init__(self, root, auto_run=False):
        self.root = root
        self.entries = entry_model.load_entries()
        self._entries_mtime = self._current_entries_mtime()
        self._last_shutdown_was_clean = settings_store.mark_session_started()
        self._exiting = False
        self._tray_icon = None
        self._control_server = None
        self._instance_guard = None
        self._auto_run = auto_run
        self._scan_job_id = None
        self._checkbox_labels = {}
        self._launch_labels = {}
        self._active_edit = None
        self._suppress_global_close_count = 0
        self._sort_column = None
        self._sort_reverse = False
        self._button_bar_rows = 1
        self._layout_ready = False

        configure_ui_style(root)
        apply_window_icon(root)

        self.autostart_var = tk.BooleanVar(value=autostart.is_enabled())
        if autostart.refresh_if_enabled():
            session_log.write("autostart entry was outdated - rewritten.")

        root.title("Startup Launcher")
        root.geometry("1100x560")
        root.withdraw()

        self._build_menu()
        self._build_button_bar(root)

        tree_frame = ttk.Frame(root, padding=(10, 0))
        tree_frame.pack(fill="both", expand=True)

        self.tree = ttk.Treeview(
            tree_frame, columns=COLUMNS, show="tree headings", selectmode="browse"
        )
        for col in ("#0",) + COLUMNS:
            if col == "launch":
                self.tree.heading(col, text=COLUMN_LABELS[col])
            else:
                self.tree.heading(col, text=COLUMN_LABELS[col], command=lambda c=col: self._sort_by(c))
        self.tree.column("#0", width=220)
        self.tree.column("launch", width=55, anchor="center")
        self.tree.column("enabled", width=70, anchor="center")
        self.tree.column("mode", width=110, anchor="w")
        self.tree.column("delay", width=70, anchor="center")
        self.tree.column("command", width=290)
        self.tree.column("xy", width=100, anchor="w")
        self.tree.column("size", width=110, anchor="w")
        self.tree.pack(side="left", fill="both", expand=True)

        self._tree_scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=self._on_tree_scroll)
        self._tree_scrollbar.pack(side="right", fill="y")

        self.tree.bind("<Double-1>", self._on_tree_double_click)
        self.tree.bind("<Button-3>", self._on_tree_context_menu)
        self.tree.bind("<Configure>", lambda _e: self._position_overlays())
        self.tree.bind("<<TreeviewOpen>>", lambda _e: self.root.after_idle(self._position_overlays))
        self.tree.bind("<<TreeviewClose>>", lambda _e: self.root.after_idle(self._position_overlays))
        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        root.bind_all("<Button-1>", self._on_global_click, add="+")

        status_frame = ttk.Frame(root, padding=(10, 0, 10, 10))
        status_frame.pack(fill="both")
        self.status_var = tk.StringVar(value="Ready.")
        ttk.Label(status_frame, textvariable=self.status_var, anchor="w").pack(fill="x")

        self._build_context_menu()
        self._refresh_tree()
        self._update_action_buttons()

        root.protocol("WM_DELETE_WINDOW", self._hide_to_tray)
        root.after_idle(self._start_tray_icon)
        root.after_idle(self._start_control_server)
        root.after_idle(lambda: setattr(self, "_layout_ready", True))
        self._schedule_periodic_scan()
        self.root.after(ENTRIES_POLL_INTERVAL_MS, self._check_entries_file_changed)

        if auto_run:
            if settings_store.load_settings().get("launch_at_login", True):
                root.after(AUTOSTART_LAUNCH_DELAY_MS, self._start_all)
            else:
                session_log.write("autostart run: 'launch at login' is off, started into the tray only.")

    # -- layout -----------------------------------------------------------

    def _build_button_bar(self, root):
        self._button_bar_base_height = None
        self.button_bar = WrapButtonBar(root, on_rows_changed=self._on_button_rows_changed, padding=(10, 8))
        self.button_bar.pack(fill="x")

        self.button_bar.add("New", self._add_entry, tooltip="Add a new entry.")
        self.btn_edit = self.button_bar.add("Edit", self._edit_selected, tooltip="Edit the selected entry.")
        self.btn_delete = self.button_bar.add(
            "Delete", self._delete_selected, tooltip="Delete the selected entry or group."
        )
        self.btn_move_up = self.button_bar.add(
            "Move Up", lambda: self._move_selected(-1), tooltip="Move the selected entry up."
        )
        self.btn_move_down = self.button_bar.add(
            "Move Down", lambda: self._move_selected(1), tooltip="Move the selected entry down."
        )
        self.btn_restart = self.button_bar.add(
            "Restart",
            self._start_selected,
            style="Primary.TButton",
            tooltip="Run the selected entry or group again, regardless of its Enabled state.",
        )
        self.btn_restore = self.button_bar.add(
            "Restore Position",
            self._restore_selected,
            tooltip="Move the selected entry's (or group's) open window back to its last saved position/size.",
        )
        self.button_bar.add(
            "Start All",
            self._start_all,
            style="Primary.TButton",
            tooltip="Launch every enabled entry, like at login.",
        )

    def _on_button_rows_changed(self, rows):
        # Ignore row-count changes while the window is still being built - only react
        # to real wraps caused by the user later resizing the window narrower.
        if not self._layout_ready or rows <= self._button_bar_rows:
            self._button_bar_rows = max(self._button_bar_rows, rows)
            return

        extra_rows = rows - self._button_bar_rows
        self._button_bar_rows = rows
        row_height = self.button_bar.row_height + 4  # matches WrapButtonBar's own row spacing
        width = self.root.winfo_width() or 1100
        height = self.root.winfo_height() or 560
        self.root.geometry(f"{width}x{height + extra_rows * row_height}")

    # -- window / tray -------------------------------------------------

    def _build_menu(self):
        menubar = tk.Menu(self.root, tearoff=False)

        file_menu = tk.Menu(menubar, tearoff=False)
        file_menu.add_checkbutton(
            label="Run Automatically at Startup", variable=self.autostart_var, command=self._toggle_autostart
        )
        file_menu.add_separator()
        file_menu.add_command(label="Minimize to Tray", command=self._hide_to_tray)
        file_menu.add_command(label="Quit", command=self._quit_application)
        menubar.add_cascade(label="File", menu=file_menu)
        self._bind_menu_hints(
            file_menu,
            {
                0: "Launch this app at login and start all enabled entries automatically.",
                2: "Hide the window - the app keeps running in the tray.",
                3: "Close the app completely.",
            },
        )

        positions_menu = tk.Menu(menubar, tearoff=False)
        positions_menu.add_command(label="Scan Now", command=self._scan_now)
        positions_menu.add_separator()
        positions_menu.add_command(label="Settings...", command=self._open_settings)
        menubar.add_cascade(label="Window Positions", menu=positions_menu)
        self._bind_menu_hints(
            positions_menu,
            {
                0: "Scan all open windows now and save their position/size.",
                2: "Configure the scan interval and startup position restore.",
            },
        )

        help_menu = tk.Menu(menubar, tearoff=False)
        help_menu.add_command(label="Startup Log...", command=self._show_session_log)
        help_menu.add_separator()
        help_menu.add_command(label="About", command=self._show_about)
        help_menu.add_command(label="Developer", command=self._show_developer)
        menubar.add_cascade(label="Help", menu=help_menu)
        self._bind_menu_hints(
            help_menu,
            {
                0: "Show what happened during the last (auto)starts.",
                2: "Show what this app does.",
                3: "Show developer/contact info.",
            },
        )

        self.root.config(menu=menubar)

    def _bind_menu_hints(self, menu, hints):
        """Show a short description in the status bar while a menu entry is highlighted."""

        def on_select(_event=None):
            index = menu.index("active")
            if index in hints:
                self._log(hints[index])

        menu.bind("<<MenuSelect>>", on_select)

    def _show_about(self):
        messagebox.showinfo(
            "About Startup Launcher",
            "Startup Launcher\n\n"
            "Configure, launch, and restore the window positions of your "
            "login startup programs.",
        )

    def _show_session_log(self):
        """Show the tail of the startup log - the only record an autostart run leaves."""
        try:
            lines = SESSION_LOG_FILE.read_text(encoding="utf-8").splitlines()
        except OSError:
            lines = []

        tail = "\n".join(lines[-SESSION_LOG_TAIL_LINES:]) if lines else "(no entries yet)"
        messagebox.showinfo("Startup Log", f"{SESSION_LOG_FILE}\n\n{tail}")

    def _show_developer(self):
        messagebox.showinfo(
            "Developer",
            "Joachim Ruf\n"
            "Loresoft\n\n"
            "GitHub: https://github.com/joruf\n"
            "Web: https://www.loresoft.de/",
        )

    def _start_tray_icon(self):
        tray = TrayIcon(
            icon_path=ICON_FILE,
            tooltip="Startup Launcher",
            on_show=lambda: self.root.after(0, self._show_from_tray),
            on_exit=lambda: self.root.after(0, self._quit_application),
            autostart_getter=lambda: self.autostart_var.get(),
            on_toggle_autostart=lambda enabled: self.root.after(0, lambda: self._set_autostart_from_tray(enabled)),
        )
        if tray.start():
            self._tray_icon = tray
            if not self._auto_run:
                # Only the login run is meant to stay invisible. Started by hand the
                # window has to come up, otherwise the app looks like it didn't start
                # at all - the whole window is built withdrawn (see __init__).
                self._show_from_tray()
        elif self._auto_run:
            # Started via autostart: stay tray-only no matter what, even without a
            # tray icon to show for it - open the app manually later to fix GTK3
            # or to reach the window.
            self._log("System tray unavailable (GTK3 bindings missing). Staying hidden (autostart run).")
            session_log.write("autostart run: system tray unavailable (GTK3 bindings missing).")
        else:
            self._log("System tray unavailable (GTK3 bindings missing). Window stays open.")
            self.root.deiconify()
            self.root.after_idle(self._position_overlays)

    def _start_control_server(self):
        self._control_server = InstanceControlServer(on_show=lambda: self.root.after(0, self._show_from_tray))
        self._control_server.start()

    def _hide_to_tray(self):
        self.root.withdraw()
        self._log("Running in the system tray.")

    def _show_from_tray(self):
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()
        self.root.after_idle(self._position_overlays)

    def _quit_application(self):
        if self._exiting:
            return
        self._exiting = True
        self._log("Saving window positions before exit ...")
        geometry_service.scan_and_store(self.entries, log=self._log)
        settings_store.mark_clean_shutdown()
        if self._control_server is not None:
            self._control_server.stop()
            self._control_server = None
        if self._instance_guard is not None:
            self._instance_guard.release()
            self._instance_guard = None
        self.root.destroy()

    # -- helpers ---------------------------------------------------------

    def _log(self, message):
        """
        Show a message in the status line, from any thread.

        Tk/Tcl belongs to the thread that runs the mainloop, and launcher.py logs
        from its window-state worker threads. Touching the widget from there is a
        coin flip between "works", "RuntimeError: main thread is not in main loop"
        and taking the whole process down - which is exactly what an autostart run
        cannot afford, since it would abort the login sequence halfway through.
        """
        if threading.current_thread() is threading.main_thread():
            self.status_var.set(message)
            return

        try:
            self.root.after(0, self.status_var.set, message)
        except (tk.TclError, RuntimeError):
            pass  # interpreter already gone; a status line is not worth a crash

    def _current_entries_mtime(self):
        try:
            return ENTRIES_FILE.stat().st_mtime
        except OSError:
            return None

    def _check_entries_file_changed(self):
        mtime = self._current_entries_mtime()
        if mtime != self._entries_mtime:
            self._entries_mtime = mtime
            self.entries = entry_model.load_entries()
            self._refresh_tree()
            self._log("entries.json changed on disk - table reloaded.")
        self.root.after(ENTRIES_POLL_INTERVAL_MS, self._check_entries_file_changed)

    def _refresh_tree(self):
        self._cancel_inline_edit()
        selected = self.tree.selection()
        self.tree.delete(*self.tree.get_children())
        saved_geometry = geometry_model.load_geometry()
        group_ids = {}
        empty_values = ("",) * len(COLUMNS)
        for index, entry in enumerate(self.entries):
            group = entry.get("group", "").strip()
            parent = ""
            if group:
                parent = group_ids.get(group)
                if parent is None:
                    parent = f"g:{group}"
                    self.tree.insert("", "end", iid=parent, text=group, open=True, values=empty_values)
                    group_ids[group] = parent

            geometry = saved_geometry.get(entry["id"])
            self.tree.insert(
                parent,
                "end",
                iid=f"e{index}",
                text=entry["name"],
                values=(
                    "",
                    CHECKED if entry.get("enabled", True) else UNCHECKED,
                    entry_model.WINDOW_MODE_LABELS[entry["window_mode"]],
                    str(entry.get("delay_seconds", 0)),
                    _flatten_command(entry["command"]),
                    _format_xy(geometry),
                    _format_size(geometry),
                ),
            )

        for group, gid in group_ids.items():
            children = self.tree.get_children(gid)
            states = [self.tree.set(c, "enabled") == CHECKED for c in children]
            if all(states):
                self.tree.set(gid, "enabled", CHECKED)
            elif not any(states):
                self.tree.set(gid, "enabled", UNCHECKED)
            else:
                self.tree.set(gid, "enabled", PARTIAL)

        if selected and self.tree.exists(selected[0]):
            self.tree.selection_set(selected[0])

        self.root.after_idle(self._position_overlays)

    def _selected_id(self):
        selection = self.tree.selection()
        return selection[0] if selection else None

    @staticmethod
    def _is_group(iid):
        return iid is not None and iid.startswith("g:")

    @staticmethod
    def _entry_index(iid):
        if iid is not None and iid.startswith("e"):
            return int(iid[1:])
        return None

    def _save(self):
        entry_model.save_entries(self.entries)
        self._entries_mtime = self._current_entries_mtime()

    # -- sorting ------------------------------------------------------------

    def _sort_by(self, column):
        self._cancel_inline_edit()
        reverse = self._sort_column == column and not self._sort_reverse
        self._sort_column = column
        self._sort_reverse = reverse

        geometry = geometry_model.load_geometry()
        self.entries.sort(key=lambda e: self._sort_key(e, column, geometry), reverse=reverse)
        self._save()
        self._update_sort_indicators()
        self._refresh_tree()

    def _sort_key(self, entry, column, geometry):
        if column == "#0":
            return entry["name"].lower()
        if column == "enabled":
            return bool(entry.get("enabled", True))
        if column == "mode":
            return entry_model.WINDOW_MODE_LABELS[entry["window_mode"]].lower()
        if column == "delay":
            return entry.get("delay_seconds", 0)
        if column == "command":
            return entry["command"].lower()
        if column in ("xy", "size"):
            saved = geometry.get(entry["id"])
            if not saved:
                return (float("inf"), float("inf"))
            return (saved["x"], saved["y"]) if column == "xy" else (saved["width"], saved["height"])
        return ""

    def _update_sort_indicators(self):
        for col, label in COLUMN_LABELS.items():
            text = label
            if col == self._sort_column:
                text += " ▼" if self._sort_reverse else " ▲"
            self.tree.heading(col, text=text)

    # -- row selection / context menu --------------------------------------

    def _on_tree_select(self, _event=None):
        self._position_overlays()
        self._update_action_buttons()

    def _update_action_buttons(self):
        iid = self._selected_id()
        has_selection = iid is not None
        is_group = has_selection and self._is_group(iid)

        self.btn_restart.configure(state="normal" if has_selection else "disabled")
        self.btn_restore.configure(state="normal" if has_selection else "disabled")
        self.btn_delete.configure(state="normal" if has_selection else "disabled")
        self.btn_edit.configure(state="normal" if has_selection and not is_group else "disabled")
        self.btn_move_up.configure(state="normal" if has_selection and not is_group else "disabled")
        self.btn_move_down.configure(state="normal" if has_selection and not is_group else "disabled")

    def _build_context_menu(self):
        self.context_menu = tk.Menu(self.root, tearoff=False)
        self.context_menu.add_command(label="Restart", command=self._start_selected)
        self.context_menu.add_command(label="Restore Position", command=self._restore_selected)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="Edit...", command=self._edit_selected)
        self.context_menu.add_command(label="Delete...", command=self._delete_selected)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="Move Up", command=lambda: self._move_selected(-1))
        self.context_menu.add_command(label="Move Down", command=lambda: self._move_selected(1))

    def _on_tree_context_menu(self, event):
        iid = self.tree.identify_row(event.y)
        if not iid:
            return

        self._cancel_inline_edit()
        self.tree.selection_set(iid)
        self.tree.focus(iid)
        self._update_action_buttons()

        entry_only_state = "disabled" if self._is_group(iid) else "normal"
        self.context_menu.entryconfig("Edit...", state=entry_only_state)
        self.context_menu.entryconfig("Move Up", state=entry_only_state)
        self.context_menu.entryconfig("Move Down", state=entry_only_state)

        self.context_menu.tk_popup(event.x_root, event.y_root)

    # -- checkbox / launch-button overlays ----------------------------------

    def _on_tree_scroll(self, first, last):
        self._tree_scrollbar.set(first, last)
        self._position_overlays()

    def _all_iids(self, parent=""):
        result = []
        for iid in self.tree.get_children(parent):
            result.append(iid)
            result.extend(self._all_iids(iid))
        return result

    def _checkbox_state(self, iid):
        if self._is_group(iid):
            return self.tree.set(iid, "enabled")
        index = self._entry_index(iid)
        return CHECKED if self.entries[index].get("enabled", True) else UNCHECKED

    def _position_overlays(self):
        """Redraw both the per-row Enabled checkbox and Launch button overlays."""
        self._rebuild_column_overlay(
            "enabled", self._checkbox_labels, self._checkbox_overlay_style, self._on_checkbox_click
        )
        self._rebuild_column_overlay(
            "launch", self._launch_labels, self._launch_overlay_style, self._on_launch_click
        )

    def _checkbox_overlay_style(self, iid):
        state = self._checkbox_state(iid)
        return state, MUTED_FG if state == UNCHECKED else TEXT_FG

    def _launch_overlay_style(self, _iid):
        return LAUNCH_GLYPH, TEXT_FG

    def _rebuild_column_overlay(self, column, labels, style_fn, on_click):
        """
        Recreate the clickable Label overlays for one Treeview data column.

        ttk.Treeview can't render a bigger glyph or a clickable "button" in a
        plain data column, so both the Enabled checkbox and the Launch button
        are drawn as real widgets placed on top of their cell instead.
        """
        for label in labels.values():
            label.destroy()
        labels.clear()

        for iid in self._all_iids():
            bbox = self.tree.bbox(iid, column=column)
            if not bbox:
                continue
            x, y, width, height = bbox

            text, foreground = style_fn(iid)
            is_selected = iid in self.tree.selection()
            label = tk.Label(
                self.tree,
                text=text,
                font=CHECKBOX_FONT,
                background=SELECTION_COLOR if is_selected else PANEL_BG,
                foreground=foreground,
                cursor="hand2",
            )
            label.place(x=x, y=y, width=width, height=height)
            label.bind("<Button-1>", lambda _e, target=iid: on_click(target))
            labels[iid] = label

    def _on_checkbox_click(self, iid):
        self._cancel_inline_edit()
        self.tree.selection_set(iid)
        if self._is_group(iid):
            self._toggle_group(iid[2:])
        else:
            self._toggle_entry(self._entry_index(iid))

    def _on_launch_click(self, iid):
        self._cancel_inline_edit()
        self.tree.selection_set(iid)
        self._start_selected()

    def _toggle_entry(self, index):
        entry = self.entries[index]
        entry["enabled"] = not entry.get("enabled", True)
        self._save()
        self._refresh_tree()

    def _toggle_group(self, group):
        members = [e for e in self.entries if e.get("group", "").strip() == group]
        if not members:
            return
        new_state = not all(e.get("enabled", True) for e in members)
        for entry in members:
            entry["enabled"] = new_state
        self._save()
        self._refresh_tree()

    # -- inline cell editing -------------------------------------------------

    def _on_tree_double_click(self, event):
        if self.tree.identify_region(event.x, event.y) not in ("cell", "tree"):
            return
        treecol = self.tree.identify_column(event.x)
        field = EDITABLE_FIELD_BY_TREECOL.get(treecol)
        if field is None:
            return
        iid = self.tree.identify_row(event.y)
        if not iid or self._is_group(iid):
            return
        self._begin_inline_edit(iid, treecol, field)

    def _begin_inline_edit(self, iid, treecol, field):
        self._cancel_inline_edit()

        bbox = self.tree.bbox(iid) if treecol == "#0" else self.tree.bbox(iid, column=treecol)
        if not bbox:
            return
        x, y, width, height = bbox
        index = self._entry_index(iid)
        entry = self.entries[index]

        if field == "name":
            current_text = entry["name"]
        elif field == "command":
            current_text = _flatten_command(entry["command"])
        elif field == "delay":
            current_text = str(entry.get("delay_seconds", 0))
        else:
            saved = geometry_model.load_geometry().get(entry["id"])
            current_text = _format_xy(saved) if field == "xy" else _format_size(saved)

        var = tk.StringVar(value=current_text)
        if field == "delay":
            widget = ttk.Spinbox(
                self.tree, from_=0, to=60, textvariable=var, width=5, font=INLINE_EDIT_FONT
            )
        else:
            widget = ttk.Entry(self.tree, textvariable=var, font=INLINE_EDIT_FONT)

        # A row-height-tall Entry/Spinbox clips text at the bottom (its internal
        # padding eats into the cell's exact pixel height), so give it enough
        # extra room to fit its own natural size and re-center it on the row
        # instead of just growing downward.
        widget.update_idletasks()
        pad = max(8, widget.winfo_reqheight() - height + 2)
        widget.place(x=x, y=y - pad // 2, width=width, height=height + pad)
        widget.focus_set()
        widget.select_range(0, "end")
        widget.bind("<Return>", lambda _e: self._commit_inline_edit())
        widget.bind("<KP_Enter>", lambda _e: self._commit_inline_edit())
        widget.bind("<Escape>", lambda _e: self._cancel_inline_edit())
        widget.bind("<FocusOut>", lambda _e: self._commit_inline_edit())

        # Keep a Python reference to `var` for as long as the widget lives: a
        # tk.StringVar with no remaining Python references gets garbage-collected,
        # which unsets its underlying Tcl variable and blanks the Entry/Spinbox -
        # exactly the "no previous text shown" bug this fixes.
        self._active_edit = {"widget": widget, "var": var, "index": index, "field": field}
        # Opening the editor takes a double-click - both of its two raw Button-1
        # presses also reach _on_global_click (via bind_all) right after; without
        # this, one of them would immediately close what it just opened.
        self._suppress_global_close_count = 2

    def _on_global_click(self, event):
        clicked = event.widget
        self.root.after_idle(lambda: self._maybe_close_inline_edit(clicked))

    def _maybe_close_inline_edit(self, clicked_widget):
        if self._suppress_global_close_count > 0:
            self._suppress_global_close_count -= 1
            return
        if self._active_edit is None or clicked_widget is self._active_edit["widget"]:
            return
        self._commit_inline_edit()

    def _cancel_inline_edit(self):
        if self._active_edit is None:
            return
        edit = self._active_edit
        self._active_edit = None
        edit["widget"].destroy()

    def _commit_inline_edit(self):
        if self._active_edit is None:
            return
        edit = self._active_edit
        self._active_edit = None
        widget = edit["widget"]
        value = widget.get().strip()
        widget.destroy()

        entry = self.entries[edit["index"]]
        field = edit["field"]

        if field == "name":
            if value:
                entry["name"] = value
                self._save()
        elif field == "command":
            if value:
                entry["command"] = value
                self._save()
        elif field == "delay":
            try:
                entry["delay_seconds"] = entry_model.clamp_delay_seconds(int(value))
            except ValueError:
                pass
            else:
                self._save()
        elif field in ("xy", "size"):
            self._commit_position_field(entry, field, value)

        self._refresh_tree()

    def _commit_position_field(self, entry, field, value):
        if not value:
            return
        geometry = geometry_model.load_geometry()
        current = dict(geometry.get(entry["id"], {"x": 0, "y": 0, "width": 800, "height": 600}))
        try:
            if field == "xy":
                x_str, y_str = value.split(",")
                current["x"] = int(x_str.strip())
                current["y"] = int(y_str.strip())
            else:
                w_str, h_str = value.lower().replace("×", "x").split("x")
                current["width"] = int(w_str.strip())
                current["height"] = int(h_str.strip())
        except (ValueError, AttributeError):
            expected = "x,y (e.g. 100,50)" if field == "xy" else "widthxheight (e.g. 1920x1080)"
            self._log(f"Invalid format for {field.upper()} - expected {expected}.")
            return

        geometry[entry["id"]] = current
        geometry_model.save_geometry(geometry)

    # -- entry actions -----------------------------------------------------

    def _add_entry(self):
        dialog = EntryDialog(self.root, existing_groups=entry_model.existing_groups(self.entries))
        self.root.wait_window(dialog)
        if dialog.result:
            dialog.result["id"] = entry_model.new_id()
            self.entries.append(dialog.result)
            self._save()
            self._refresh_tree()

    def _edit_selected(self):
        iid = self._selected_id()
        if iid is None:
            messagebox.showinfo("No Entry", "Please select an entry first.")
            return
        if self._is_group(iid):
            messagebox.showinfo("Group", "Please select a single entry inside the group.")
            return

        index = self._entry_index(iid)
        dialog = EntryDialog(
            self.root,
            entry=self.entries[index],
            existing_groups=entry_model.existing_groups(self.entries),
        )
        self.root.wait_window(dialog)
        if dialog.result:
            dialog.result["id"] = self.entries[index].get("id") or entry_model.new_id()
            self.entries[index] = dialog.result
            self._save()
            self._refresh_tree()

    def _delete_selected(self):
        iid = self._selected_id()
        if iid is None:
            messagebox.showinfo("No Entry", "Please select an entry first.")
            return

        if self._is_group(iid):
            group = iid[2:]
            indices = [i for i, e in enumerate(self.entries) if e.get("group", "").strip() == group]
            if not indices:
                return
            if messagebox.askyesno(
                "Delete Group", f"Really delete the whole group '{group}' ({len(indices)} entries)?"
            ):
                removed_ids = [self.entries[i]["id"] for i in indices]
                for i in sorted(indices, reverse=True):
                    del self.entries[i]
                self._save()
                geometry_service.forget(removed_ids)
                self._refresh_tree()
            return

        index = self._entry_index(iid)
        entry = self.entries[index]
        if messagebox.askyesno("Delete", f"Really delete '{entry['name']}'?"):
            del self.entries[index]
            self._save()
            geometry_service.forget([entry["id"]])
            self._refresh_tree()

    def _move_selected(self, offset):
        iid = self._selected_id()
        if iid is None or self._is_group(iid):
            return
        index = self._entry_index(iid)
        new_index = index + offset
        if not 0 <= new_index < len(self.entries):
            return
        self.entries[index], self.entries[new_index] = self.entries[new_index], self.entries[index]
        self._save()
        self._refresh_tree()
        self.tree.selection_set(f"e{new_index}")

    def _start_selected(self):
        iid = self._selected_id()
        if iid is None:
            messagebox.showinfo("No Entry", "Please select an entry or a group first.")
            return

        if self._is_group(iid):
            group = iid[2:]
            group_entries = [e for e in self.entries if e.get("group", "").strip() == group]
            self._log(f"Starting group '{group}' ({len(group_entries)} entries) ...")
            for entry in group_entries:
                launcher.launch_entry(entry, log=self._log)
            return

        index = self._entry_index(iid)
        entry = self.entries[index]
        self._log(f"Starting '{entry['name']}' ...")
        launcher.launch_entry(entry, log=self._log)

    def _start_all(self):
        self._log("Starting all enabled entries ...")
        restore_fn = None
        settings = settings_store.load_settings()
        if self._auto_run and self._last_shutdown_was_clean and settings.get("restore_on_startup", False):
            restore_fn = geometry_service.wait_and_restore_geometry

        enabled = [entry for entry in self.entries if entry.get("enabled", True)]
        if self._auto_run:
            session_log.write(f"autostart run: launching {len(enabled)} enabled entries.")

        launcher.launch_entries(
            self.entries,
            log=self._log,
            geometry_restore=restore_fn,
            schedule=self._schedule_delayed_launch,
        )

    def _schedule_delayed_launch(self, delay_seconds, callback):
        """Run a delayed entry's launch on the Tk clock instead of in a timer thread."""
        self.root.after(int(delay_seconds * 1000), callback)

    def _toggle_autostart(self):
        if self.autostart_var.get():
            autostart.enable()
            self._log("Autostart enabled.")
        else:
            autostart.disable()
            self._log("Autostart disabled.")

    def _set_autostart_from_tray(self, enabled):
        self.autostart_var.set(enabled)
        self._toggle_autostart()

    # -- window positions ----------------------------------------------

    def _scan_now(self):
        self._log("Scanning open windows ...")
        geometry_service.scan_and_store(self.entries, log=self._log)
        self._refresh_tree()

    def _restore_selected(self):
        iid = self._selected_id()
        if iid is None:
            messagebox.showinfo("No Entry", "Please select an entry or a group first.")
            return

        if self._is_group(iid):
            group = iid[2:]
            for entry in self.entries:
                if entry.get("group", "").strip() == group:
                    geometry_service.restore_geometry(entry, log=self._log)
            return

        index = self._entry_index(iid)
        geometry_service.restore_geometry(self.entries[index], log=self._log)

    def _open_settings(self):
        dialog = SettingsDialog(self.root)
        self.root.wait_window(dialog)
        if dialog.result:
            current = settings_store.load_settings()
            current.update(dialog.result)
            settings_store.save_settings(current)
            self._log("Settings saved.")
            self._schedule_periodic_scan(reset=True)

    def _schedule_periodic_scan(self, reset=False):
        if reset and self._scan_job_id is not None:
            self.root.after_cancel(self._scan_job_id)
            self._scan_job_id = None

        current = settings_store.load_settings()
        if not current.get("scan_enabled", True):
            return
        interval_ms = max(1, current.get("scan_interval_minutes", 10)) * 60 * 1000
        self._scan_job_id = self.root.after(interval_ms, self._run_periodic_scan)

    def _run_periodic_scan(self):
        geometry_service.scan_and_store(self.entries, log=self._log)
        self._refresh_tree()
        self._schedule_periodic_scan()


def main():
    auto_run = autostart.AUTOSTART_FLAG in sys.argv[1:]
    mode = "autostart" if auto_run else "manual"

    may_continue, instance_guard = enforce_single_instance(quiet=auto_run)
    if not may_continue:
        session_log.write(f"{mode} start refused: another instance is already running.")
        return 1

    session_log.write(f"{mode} start (pid {os.getpid()}).")
    try:
        root = tk.Tk()
        app = StartupLauncherApp(root, auto_run=auto_run)
        app._instance_guard = instance_guard
        root.mainloop()
    except BaseException:
        # An autostart run has nowhere to print a traceback to, so keep it on disk:
        # a run that dies mid-sequence otherwise leaves half-started programs and
        # no explanation.
        session_log.write(f"{mode} run failed:\n{traceback.format_exc()}")
        raise

    instance_guard.release()
    session_log.write(f"{mode} run exited normally.")
    return 0
