"""A horizontal button bar that wraps overflowing buttons onto new rows."""

import tkinter as tk
from tkinter import ttk

PADDING = 4


class WrapButtonBar(ttk.Frame):
    """
    Lays out child buttons left-to-right, wrapping to additional rows when the
    available width runs out, instead of letting buttons run off-screen.
    """

    def __init__(self, parent, on_rows_changed=None, **kwargs):
        super().__init__(parent, **kwargs)
        self._buttons = []
        self._row_height = 0
        self._row_count = 1
        self._on_rows_changed = on_rows_changed
        # Children are placed with .place(), which never influences the frame's
        # requested size - disable propagation so our own height stays in effect.
        self.pack_propagate(False)
        self.bind("<Configure>", lambda _e: self._reflow())

    @property
    def row_height(self):
        """Height in pixels of a single button row (0 until the first button is added)."""
        return self._row_height

    def add(self, text, command, style=None, tooltip=None):
        """Add a button to the bar and return it."""
        from ui.tooltip import Tooltip

        button = ttk.Button(self, text=text, command=command, style=style)
        button.update_idletasks()
        self._row_height = max(self._row_height, button.winfo_reqheight())
        self._buttons.append(button)
        if tooltip:
            Tooltip(button, tooltip)
        self._reflow()
        return button

    def _reflow(self):
        width = self.winfo_width()
        if width <= 1:
            self.after(10, self._reflow)
            return

        row_step = self._row_height + PADDING
        x = PADDING
        y = PADDING
        for button in self._buttons:
            w = button.winfo_reqwidth()
            if x > PADDING and x + w + PADDING > width:
                x = PADDING
                y += row_step
            button.place(x=x, y=y, width=w, height=self._row_height)
            x += w + PADDING

        total_height = y + self._row_height + PADDING
        rows = round(total_height / row_step)
        self.configure(height=total_height)
        if rows != self._row_count:
            self._row_count = rows
            if self._on_rows_changed:
                self._on_rows_changed(rows)
