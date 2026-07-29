"""Minimal delayed hover tooltip for tk/ttk widgets."""

import tkinter as tk

SHOW_DELAY_MS = 400


class Tooltip:
    """Attach a small delayed hover tooltip with the given text to a widget."""

    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self._after_id = None
        self._window = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")

    def _schedule(self, _event=None):
        self._after_id = self.widget.after(SHOW_DELAY_MS, self._show)

    def _show(self):
        if self._window is not None:
            return
        x = self.widget.winfo_rootx() + 8
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        self._window = tk.Toplevel(self.widget)
        self._window.wm_overrideredirect(True)
        self._window.wm_geometry(f"+{x}+{y}")
        tk.Label(
            self._window,
            text=self.text,
            background="#18181b",
            foreground="#fafafa",
            padx=8,
            pady=4,
            font=("TkDefaultFont", 9),
            relief="flat",
        ).pack()

    def _hide(self, _event=None):
        if self._after_id is not None:
            self.widget.after_cancel(self._after_id)
            self._after_id = None
        if self._window is not None:
            self._window.destroy()
            self._window = None


def attach(widget, text):
    """Attach a hover tooltip to a widget."""
    return Tooltip(widget, text)
