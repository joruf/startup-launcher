"""Modal dialog to add or edit a single launch entry."""

import tkinter as tk
from tkinter import messagebox, ttk

from models.entries import (
    MATCH_MODE_LABELS,
    MATCH_MODES,
    MAX_DELAY_SECONDS,
    MIN_DELAY_SECONDS,
    WINDOW_MODE_LABELS,
    WINDOW_MODES,
    clamp_delay_seconds,
)
from ui.style import BORDER_COLOR, FOCUS_COLOR, PANEL_BG, TEXT_FG
from ui.window_icon import apply_window_icon

COMMAND_TEXT_HEIGHT = 6


class EntryDialog(tk.Toplevel):
    """Modal dialog to add or edit a single launch entry."""

    def __init__(self, parent, entry=None, existing_groups=None):
        super().__init__(parent)
        self.result = None
        self.title("Edit Entry" if entry else "New Entry")
        self.resizable(False, False)
        self.transient(parent)
        apply_window_icon(self)
        self.grab_set()

        entry = entry or {}
        self._enabled = entry.get("enabled", True)

        form = ttk.Frame(self, padding=12)
        form.grid(row=0, column=0, sticky="nsew")

        ttk.Label(form, text="Name:").grid(row=0, column=0, sticky="w", pady=4)
        self.name_var = tk.StringVar(value=entry.get("name", ""))
        ttk.Entry(form, textvariable=self.name_var, width=60).grid(row=0, column=1, columnspan=2, sticky="we")

        ttk.Label(form, text="Command:").grid(row=1, column=0, sticky="nw", pady=4)
        command_frame = ttk.Frame(form)
        command_frame.grid(row=1, column=1, columnspan=2, sticky="we")
        self.command_text = tk.Text(
            command_frame,
            width=60,
            height=COMMAND_TEXT_HEIGHT,
            wrap="word",
            background=PANEL_BG,
            foreground=TEXT_FG,
            insertbackground=TEXT_FG,
            highlightbackground=BORDER_COLOR,
            highlightcolor=FOCUS_COLOR,
            highlightthickness=1,
            relief="flat",
            borderwidth=0,
            padx=6,
            pady=4,
        )
        self.command_text.insert("1.0", entry.get("command", ""))
        self.command_text.pack(side="left", fill="both", expand=True)
        command_scroll = ttk.Scrollbar(command_frame, orient="vertical", command=self.command_text.yview)
        self.command_text.configure(yscrollcommand=command_scroll.set)
        command_scroll.pack(side="left", fill="y")
        ttk.Label(
            form,
            text="One argument/path per line is fine - it will be joined into a single line when saved.",
        ).grid(row=2, column=1, columnspan=2, sticky="w")

        ttk.Label(form, text="Group:").grid(row=3, column=0, sticky="w", pady=4)
        self.group_var = tk.StringVar(value=entry.get("group", ""))
        ttk.Combobox(
            form, textvariable=self.group_var, values=existing_groups or [], width=27
        ).grid(row=3, column=1, sticky="w")
        ttk.Label(form, text="(e.g. 'VSCode' - leave empty for no group)").grid(
            row=3, column=2, sticky="w", padx=(6, 0)
        )

        ttk.Label(form, text="Window Mode:").grid(row=4, column=0, sticky="w", pady=4)
        self.mode_var = tk.StringVar(value=WINDOW_MODE_LABELS[entry.get("window_mode", "normal")])
        mode_box = ttk.Combobox(
            form,
            textvariable=self.mode_var,
            values=[WINDOW_MODE_LABELS[m] for m in WINDOW_MODES],
            state="readonly",
            width=20,
        )
        mode_box.grid(row=4, column=1, sticky="w")

        ttk.Label(form, text="Delay (seconds):").grid(row=5, column=0, sticky="w", pady=4)
        self.delay_var = tk.StringVar(value=str(entry.get("delay_seconds", 0)))
        ttk.Spinbox(
            form, from_=MIN_DELAY_SECONDS, to=MAX_DELAY_SECONDS, textvariable=self.delay_var, width=6
        ).grid(row=5, column=1, sticky="w")
        ttk.Label(form, text="How long to wait after app start before launching this entry.").grid(
            row=5, column=2, sticky="w", padx=(6, 0)
        )

        ttk.Label(form, text="Window Match:").grid(row=6, column=0, sticky="w", pady=4)
        self.match_mode_var = tk.StringVar(value=MATCH_MODE_LABELS[entry.get("match_mode", "class")])
        self.match_mode_box = ttk.Combobox(
            form,
            textvariable=self.match_mode_var,
            values=[MATCH_MODE_LABELS[m] for m in MATCH_MODES],
            state="readonly",
            width=26,
        )
        self.match_mode_box.grid(row=6, column=1, sticky="w")

        ttk.Label(form, text="Search Term:").grid(row=7, column=0, sticky="w", pady=4)
        self.match_string_var = tk.StringVar(value=entry.get("match_string", ""))
        self.match_string_entry = ttk.Entry(form, textvariable=self.match_string_var, width=30)
        self.match_string_entry.grid(row=7, column=1, columnspan=2, sticky="we")
        ttk.Label(
            form,
            text="Required for Minimized/Maximized/Fullscreen. Optional for Normal - set it anyway"
            " if you want Scan/Restore Position to track this window.",
            foreground="#71717a",
        ).grid(row=8, column=1, columnspan=2, sticky="w")

        button_row = ttk.Frame(form)
        button_row.grid(row=9, column=0, columnspan=3, sticky="e", pady=(12, 0))
        ttk.Button(button_row, text="Cancel", command=self.destroy).grid(row=0, column=0, padx=4)
        ttk.Button(
            button_row, text="Save", style="Primary.TButton", command=self._save
        ).grid(row=0, column=1, padx=4)

        self.bind("<Escape>", lambda _e: self.destroy())

    def _save(self):
        name = self.name_var.get().strip()
        # Keep the raw multi-line text as typed (for readability on the next edit) -
        # it's only flattened to a single shell line at actual launch time.
        command = self.command_text.get("1.0", "end").strip()
        group = self.group_var.get().strip()
        window_mode = next(key for key, label in WINDOW_MODE_LABELS.items() if label == self.mode_var.get())
        match_mode = next(
            key for key, label in MATCH_MODE_LABELS.items() if label == self.match_mode_var.get()
        )
        match_string = self.match_string_var.get().strip()

        try:
            delay_seconds = clamp_delay_seconds(int(self.delay_var.get()))
        except ValueError:
            delay_seconds = 0

        if not name:
            messagebox.showerror("Missing Value", "Please enter a name.", parent=self)
            return
        if not command:
            messagebox.showerror("Missing Value", "Please enter a command.", parent=self)
            return
        if window_mode != "normal" and not match_string:
            messagebox.showerror(
                "Missing Value",
                "Minimized/Maximized/Fullscreen require a search term "
                "(window class or title).",
                parent=self,
            )
            return

        self.result = {
            "name": name,
            "group": group,
            "command": command,
            "window_mode": window_mode,
            "match_mode": match_mode,
            "match_string": match_string,
            "delay_seconds": delay_seconds,
            "enabled": self._enabled,
        }
        self.destroy()
