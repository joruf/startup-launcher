"""Main application window for Startup Launcher."""

import sys
import tkinter as tk
from tkinter import messagebox, ttk

from config import autostart
from config import settings as settings_store
from models import entries as entry_model
from models import geometry as geometry_model
from paths import ICON_FILE
from services import geometry as geometry_service
from services import launcher
from ui.entry_dialog import EntryDialog
from ui.settings_dialog import SettingsDialog
from ui.style import MUTED_FG, PANEL_BG, SELECTION_COLOR, TEXT_FG, configure_ui_style
from ui.tooltip import Tooltip
from ui.tray import TrayIcon
from ui.window_icon import apply_window_icon

CHECKED = "☑"  # ☑
UNCHECKED = "☐"  # ☐
PARTIAL = "☒"  # ☒ (some, but not all, group members enabled)

# ttk.Treeview only lets #0 show a per-item image; the "enabled" data column
# can't render anything bigger than the rest of the row's text. So the checkbox
# is drawn with a real Label placed on top of that cell instead - this is the
# only way to make just the checkbox bigger while every other column keeps its
# normal size.
CHECKBOX_FONT = ("TkDefaultFont", 15)


def _format_position(saved):
    """Return a compact "x,y  WxH" label for a saved geometry, or "" if unknown."""
    if not saved:
        return ""
    return f"{saved['x']},{saved['y']}  {saved['width']}×{saved['height']}"


class StartupLauncherApp:
    """Main application window."""

    COLUMNS = ("enabled", "mode", "command", "position")

    def __init__(self, root, auto_run=False):
        self.root = root
        self.entries = entry_model.load_entries()
        self._exiting = False
        self._tray_icon = None
        self._auto_run = auto_run
        self._scan_job_id = None
        self._checkbox_labels = {}

        configure_ui_style(root)
        apply_window_icon(root)

        root.title("Startup Launcher")
        root.geometry("900x480")
        root.withdraw()

        self._build_menu()

        top_bar = ttk.Frame(root, padding=(10, 8))
        top_bar.pack(fill="x")

        self.autostart_var = tk.BooleanVar(value=autostart.is_enabled())
        autostart_check = ttk.Checkbutton(
            top_bar,
            text="Run automatically at system startup",
            variable=self.autostart_var,
            command=self._toggle_autostart,
        )
        autostart_check.pack(side="left")
        Tooltip(autostart_check, "Launch this app at login and start all enabled entries automatically.")

        tree_frame = ttk.Frame(root, padding=(10, 0))
        tree_frame.pack(fill="both", expand=True)

        self.tree = ttk.Treeview(
            tree_frame, columns=self.COLUMNS, show="tree headings", selectmode="browse"
        )
        self.tree.heading("#0", text="Name")
        self.tree.heading("enabled", text="Enabled")
        self.tree.heading("mode", text="Window Mode")
        self.tree.heading("command", text="Command")
        self.tree.heading("position", text="Position")
        self.tree.column("#0", width=240)
        self.tree.column("enabled", width=70, anchor="center")
        self.tree.column("mode", width=100, anchor="center")
        self.tree.column("command", width=340)
        self.tree.column("position", width=130, anchor="center")
        self.tree.pack(side="left", fill="both", expand=True)

        self._tree_scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=self._on_tree_scroll)
        self._tree_scrollbar.pack(side="right", fill="y")

        self.tree.bind("<Double-1>", self._on_double_click)
        self.tree.bind("<Button-3>", self._on_tree_context_menu)
        self.tree.bind("<Configure>", lambda _e: self._position_checkbox_overlays())
        self.tree.bind("<<TreeviewOpen>>", lambda _e: self.root.after_idle(self._position_checkbox_overlays))
        self.tree.bind("<<TreeviewClose>>", lambda _e: self.root.after_idle(self._position_checkbox_overlays))
        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)

        button_bar = ttk.Frame(root, padding=10)
        button_bar.pack(fill="x")

        def add_button(text, command, style=None, tooltip=None, side="left"):
            button = ttk.Button(button_bar, text=text, command=command, style=style)
            button.pack(side=side, padx=2)
            if tooltip:
                Tooltip(button, tooltip)
            return button

        add_button("New", self._add_entry, tooltip="Add a new entry.")
        self.btn_edit = add_button("Edit", self._edit_selected, tooltip="Edit the selected entry.")
        self.btn_delete = add_button(
            "Delete", self._delete_selected, tooltip="Delete the selected entry or group."
        )
        self.btn_move_up = add_button(
            "Move Up", lambda: self._move_selected(-1), tooltip="Move the selected entry up."
        )
        self.btn_move_down = add_button(
            "Move Down", lambda: self._move_selected(1), tooltip="Move the selected entry down."
        )
        self.btn_restart = add_button(
            "Restart",
            self._start_selected,
            style="Primary.TButton",
            tooltip="Run the selected entry or group again, regardless of its Enabled state.",
        )
        self.btn_restore = add_button(
            "Restore Position",
            self._restore_selected,
            tooltip="Move the selected entry's (or group's) open window back to its last saved position/size.",
        )
        add_button(
            "Start All",
            self._start_all,
            style="Primary.TButton",
            tooltip="Launch every enabled entry, like at login.",
            side="right",
        )

        status_frame = ttk.Frame(root, padding=(10, 0, 10, 10))
        status_frame.pack(fill="both")
        self.status_var = tk.StringVar(value="Ready.")
        ttk.Label(status_frame, textvariable=self.status_var, anchor="w").pack(fill="x")

        self._build_context_menu()
        self._refresh_tree()
        self._update_action_buttons()

        root.protocol("WM_DELETE_WINDOW", self._hide_to_tray)
        root.after_idle(self._start_tray_icon)
        self._schedule_periodic_scan()

        if auto_run:
            root.after(300, self._start_all)

    # -- window / tray -------------------------------------------------

    def _build_menu(self):
        menubar = tk.Menu(self.root)

        file_menu = tk.Menu(menubar, tearoff=False)
        file_menu.add_command(label="Minimize to Tray", command=self._hide_to_tray)
        file_menu.add_command(label="Quit", command=self._quit_application)
        menubar.add_cascade(label="File", menu=file_menu)
        self._bind_menu_hints(
            file_menu,
            {
                0: "Hide the window - the app keeps running in the tray.",
                1: "Close the app completely.",
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
        help_menu.add_command(label="About", command=self._show_about)
        help_menu.add_command(label="Developer", command=self._show_developer)
        menubar.add_cascade(label="Help", menu=help_menu)
        self._bind_menu_hints(
            help_menu,
            {
                0: "Show what this app does.",
                1: "Show developer/contact info.",
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
        )
        if tray.start():
            self._tray_icon = tray
        else:
            self._log("System tray unavailable (GTK3 bindings missing). Window stays open.")
            self.root.deiconify()
            self.root.after_idle(self._position_checkbox_overlays)

    def _hide_to_tray(self):
        self.root.withdraw()
        self._log("Running in the system tray.")

    def _show_from_tray(self):
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()
        self.root.after_idle(self._position_checkbox_overlays)

    def _quit_application(self):
        if self._exiting:
            return
        self._exiting = True
        self.root.destroy()

    # -- helpers ---------------------------------------------------------

    def _log(self, message):
        self.status_var.set(message)

    def _refresh_tree(self):
        selected = self.tree.selection()
        self.tree.delete(*self.tree.get_children())
        saved_geometry = geometry_model.load_geometry()
        group_ids = {}
        for index, entry in enumerate(self.entries):
            group = entry.get("group", "").strip()
            parent = ""
            if group:
                parent = group_ids.get(group)
                if parent is None:
                    parent = f"g:{group}"
                    self.tree.insert("", "end", iid=parent, text=group, open=True, values=("", "", "", ""))
                    group_ids[group] = parent

            self.tree.insert(
                parent,
                "end",
                iid=f"e{index}",
                text=entry["name"],
                values=(
                    CHECKED if entry.get("enabled", True) else UNCHECKED,
                    entry_model.WINDOW_MODE_LABELS[entry["window_mode"]],
                    entry["command"],
                    _format_position(saved_geometry.get(entry["id"])),
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

        self.root.after_idle(self._position_checkbox_overlays)

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

    # -- row selection / context menu --------------------------------------

    def _on_tree_select(self, _event=None):
        self._position_checkbox_overlays()
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

        self.tree.selection_set(iid)
        self.tree.focus(iid)
        self._update_action_buttons()

        entry_only_state = "disabled" if self._is_group(iid) else "normal"
        self.context_menu.entryconfig("Edit...", state=entry_only_state)
        self.context_menu.entryconfig("Move Up", state=entry_only_state)
        self.context_menu.entryconfig("Move Down", state=entry_only_state)

        self.context_menu.tk_popup(event.x_root, event.y_root)

    # -- checkbox toggling -------------------------------------------------

    def _on_tree_scroll(self, first, last):
        self._tree_scrollbar.set(first, last)
        self._position_checkbox_overlays()

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

    def _position_checkbox_overlays(self):
        for label in self._checkbox_labels.values():
            label.destroy()
        self._checkbox_labels = {}

        for iid in self._all_iids():
            bbox = self.tree.bbox(iid, column="enabled")
            if not bbox:
                continue
            x, y, width, height = bbox

            state = self._checkbox_state(iid)
            is_selected = iid in self.tree.selection()
            label = tk.Label(
                self.tree,
                text=state,
                font=CHECKBOX_FONT,
                background=SELECTION_COLOR if is_selected else PANEL_BG,
                foreground=MUTED_FG if state == UNCHECKED else TEXT_FG,
                cursor="hand2",
            )
            label.place(x=x, y=y, width=width, height=height)
            label.bind("<Button-1>", lambda _e, target=iid: self._on_checkbox_click(target))
            self._checkbox_labels[iid] = label

    def _on_checkbox_click(self, iid):
        self.tree.selection_set(iid)
        if self._is_group(iid):
            self._toggle_group(iid[2:])
        else:
            self._toggle_entry(self._entry_index(iid))

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

    def _on_double_click(self, _event):
        self._start_selected()

    def _start_all(self):
        self._log("Starting all enabled entries ...")
        restore_fn = None
        if self._auto_run and settings_store.load_settings().get("restore_on_startup", False):
            restore_fn = geometry_service.wait_and_restore_geometry
        launcher.launch_entries(self.entries, log=self._log, geometry_restore=restore_fn)

    def _toggle_autostart(self):
        if self.autostart_var.get():
            autostart.enable()
            self._log("Autostart enabled.")
        else:
            autostart.disable()
            self._log("Autostart disabled.")

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
            settings_store.save_settings(dialog.result)
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
    auto_run = "--autostart" in sys.argv[1:]
    root = tk.Tk()
    StartupLauncherApp(root, auto_run=auto_run)
    root.mainloop()
    return 0
