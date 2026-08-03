"""Modal dialog for application-wide settings."""

import tkinter as tk
from tkinter import ttk

from config import settings as settings_store
from ui.window_icon import apply_window_icon

SCAN_INTERVAL_CHOICES = [1, 5, 10, 15, 30, 60, 120]


class SettingsDialog(tk.Toplevel):
    """Dialog to configure window-position scanning, the login launch, and startup restore."""

    def __init__(self, parent):
        super().__init__(parent)
        self.result = None
        self.title("Settings")
        self.resizable(False, False)
        self.transient(parent)
        apply_window_icon(self)
        self.grab_set()

        current = settings_store.load_settings()

        form = ttk.Frame(self, padding=12)
        form.grid(row=0, column=0, sticky="nsew")

        self.scan_enabled_var = tk.BooleanVar(value=current["scan_enabled"])
        ttk.Checkbutton(
            form,
            text="Periodically scan open windows and remember their position/size",
            variable=self.scan_enabled_var,
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=4)

        ttk.Label(form, text="Scan interval (minutes):").grid(row=1, column=0, sticky="w", pady=4)
        self.interval_var = tk.StringVar(value=str(current["scan_interval_minutes"]))
        ttk.Combobox(
            form,
            textvariable=self.interval_var,
            values=[str(choice) for choice in SCAN_INTERVAL_CHOICES],
            width=10,
        ).grid(row=1, column=1, sticky="w")

        ttk.Separator(form, orient="horizontal").grid(
            row=2, column=0, columnspan=2, sticky="we", pady=10
        )

        self.launch_at_login_var = tk.BooleanVar(value=current["launch_at_login"])
        ttk.Checkbutton(
            form,
            text="Launch the enabled entries automatically at login",
            variable=self.launch_at_login_var,
        ).grid(row=3, column=0, columnspan=2, sticky="w", pady=(0, 4))
        ttk.Label(
            form,
            text=(
                "Needs \"Run Automatically at Startup\" (File menu) as well: that one\n"
                "starts the launcher itself at login, this one decides whether it then\n"
                "runs your programs or just waits in the tray."
            ),
            foreground="#71717a",
        ).grid(row=4, column=0, columnspan=2, sticky="w")

        ttk.Separator(form, orient="horizontal").grid(
            row=5, column=0, columnspan=2, sticky="we", pady=10
        )

        self.restore_var = tk.BooleanVar(value=current["restore_on_startup"])
        ttk.Checkbutton(
            form,
            text="Restore saved window positions automatically at startup",
            variable=self.restore_var,
        ).grid(row=6, column=0, columnspan=2, sticky="w", pady=(0, 4))
        ttk.Label(
            form,
            text=(
                "Off by default. Turn on once \"Restore Position\" in the table\n"
                "produces the layout you want - this then applies it automatically\n"
                "on the next login."
            ),
            foreground="#71717a",
        ).grid(row=7, column=0, columnspan=2, sticky="w")

        button_row = ttk.Frame(form)
        button_row.grid(row=8, column=0, columnspan=2, sticky="e", pady=(16, 0))
        ttk.Button(button_row, text="Cancel", command=self.destroy).grid(row=0, column=0, padx=4)
        ttk.Button(
            button_row, text="Save", style="Primary.TButton", command=self._save
        ).grid(row=0, column=1, padx=4)

        self.bind("<Escape>", lambda _e: self.destroy())

    def _save(self):
        try:
            interval = int(self.interval_var.get())
        except (ValueError, tk.TclError):
            interval = 10
        interval = max(1, interval)

        self.result = {
            "scan_enabled": self.scan_enabled_var.get(),
            "scan_interval_minutes": interval,
            "launch_at_login": self.launch_at_login_var.get(),
            "restore_on_startup": self.restore_var.get(),
        }
        self.destroy()
