"""Ttk theme shared with DevServer Commander for a consistent look across tools."""

import tkinter as tk
from tkinter import ttk

# Exposed so plain tk widgets (e.g. tk.Text, and the checkbox-overlay Labels used
# in the Treeview, which ttk has no per-cell equivalent for) can be styled to
# match the ttk theme below.
PANEL_BG = "#ffffff"
TEXT_FG = "#18181b"
MUTED_FG = "#71717a"
BORDER_COLOR = "#e4e4e7"
FOCUS_COLOR = "#a1a1aa"
SELECTION_COLOR = "#e4e4e7"


def configure_ui_style(root: tk.Misc) -> None:
    """Apply the same modern neutral-gray ttk theme used by DevServer Commander."""
    style = ttk.Style(root)
    available_themes = set(style.theme_names())
    if "clam" in available_themes:
        style.theme_use("clam")

    bg = "#f4f4f5"
    panel_bg = PANEL_BG
    fg = TEXT_FG
    muted_fg = "#71717a"
    border = BORDER_COLOR
    accent = "#3f3f46"
    accent_hover = "#27272a"
    accent_pressed = "#18181b"
    selection = "#e4e4e7"
    focus = FOCUS_COLOR

    root.configure(background=bg)
    root.option_add("*Background", bg)
    root.option_add("*Foreground", fg)
    root.option_add("*Font", "TkDefaultFont 10")
    root.option_add("*Menu.Background", panel_bg)
    root.option_add("*Menu.Foreground", fg)
    root.option_add("*Menu.ActiveBackground", accent)
    root.option_add("*Menu.ActiveForeground", "#fafafa")

    style.configure(".", background=bg, foreground=fg)
    style.configure("TFrame", background=bg)
    style.configure("TLabelframe", background=bg, bordercolor=border, relief="flat")
    style.configure("TLabelframe.Label", background=bg, foreground=muted_fg)
    style.configure("TLabel", background=bg, foreground=fg)
    style.configure(
        "TButton",
        padding=(12, 7),
        background=panel_bg,
        foreground=fg,
        borderwidth=1,
        bordercolor=border,
        focusthickness=1,
        focuscolor=focus,
        relief="flat",
    )
    style.map(
        "TButton",
        background=[("active", "#fafafa"), ("pressed", "#f4f4f5"), ("disabled", bg)],
        foreground=[("disabled", "#a1a1aa")],
        bordercolor=[("active", "#d4d4d8"), ("disabled", border)],
    )
    style.configure(
        "Primary.TButton",
        padding=(12, 7),
        background=accent,
        foreground="#fafafa",
        borderwidth=0,
        focusthickness=0,
        relief="flat",
    )
    style.map(
        "Primary.TButton",
        background=[
            ("active", accent_hover),
            ("pressed", accent_pressed),
            ("disabled", "#a1a1aa"),
        ],
        foreground=[("disabled", "#f4f4f5")],
    )
    style.configure(
        "TMenubutton",
        padding=(10, 6),
        background=panel_bg,
        foreground=fg,
        borderwidth=1,
        relief="flat",
    )
    style.map(
        "TMenubutton",
        background=[("active", "#fafafa")],
        bordercolor=[("focus", focus)],
    )
    style.configure(
        "TEntry",
        padding=(8, 6),
        fieldbackground=panel_bg,
        foreground=fg,
        bordercolor=border,
        lightcolor=border,
        darkcolor=border,
        relief="flat",
    )
    style.map(
        "TEntry",
        bordercolor=[("focus", focus)],
        lightcolor=[("focus", focus)],
        darkcolor=[("focus", focus)],
    )
    style.configure(
        "TCombobox",
        padding=(8, 6),
        fieldbackground=panel_bg,
        foreground=fg,
        bordercolor=border,
        arrowsize=13,
    )
    style.map(
        "TCombobox",
        fieldbackground=[("readonly", panel_bg)],
        bordercolor=[("focus", focus)],
        lightcolor=[("focus", focus)],
        darkcolor=[("focus", focus)],
    )
    style.configure(
        "Treeview",
        rowheight=26,
        background=panel_bg,
        fieldbackground=panel_bg,
        foreground=fg,
        bordercolor=border,
        lightcolor=border,
        darkcolor=border,
    )
    style.map(
        "Treeview",
        background=[("selected", selection)],
        foreground=[("selected", fg)],
    )
    style.configure(
        "Treeview.Heading",
        padding=(10, 7),
        background=bg,
        foreground=muted_fg,
        bordercolor=border,
        relief="flat",
    )
    style.map("Treeview.Heading", background=[("active", "#fafafa")], foreground=[("active", fg)])
