"""
Shared color palette and ttk style configuration.

Pulled out into its own module (rather than living as class attributes on
EresetaApp) so that TemplateEditor can use the same palette without
importing app.py — the old code had TemplateEditor reach into
`EresetaApp.COLOR_SURFACE` etc., which only worked because of import
order and would have broken the moment either module was imported on its
own or reorganized.
oh cant you see, you belong to me       
"""

from __future__ import annotations

from tkinter import Tk, font as tkfont
from tkinter import ttk

COLOR_BG = "#eef2f6"          # app background
COLOR_SURFACE = "#ffffff"     # cards / panels
COLOR_BORDER = "#cbd5e1"
COLOR_ACCENT = "#173b63"      # requested navy blue
COLOR_ACCENT_DARK = "#102b49"
COLOR_ACCENT_SOFT = "#e2e8f0"
COLOR_TEXT = "#0f172a"
COLOR_MUTED = "#526479"
COLOR_DANGER = "#c2413b"
COLOR_DANGER_DARK = "#9f302c"


def configure_styles(root: Tk) -> ttk.Style:
    """Apply the app's ttk theme to *root*. Returns the ttk.Style instance."""
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except Exception:
        pass

    root.configure(bg=COLOR_BG)

    base_font = ("Segoe UI", 10)
    try:
        tkfont.nametofont("TkDefaultFont").configure(family="Segoe UI", size=10)
        tkfont.nametofont("TkTextFont").configure(family="Segoe UI", size=10)
        tkfont.nametofont("TkHeadingFont").configure(family="Segoe UI", size=10)
    except Exception:
        pass

    style.configure(".", background=COLOR_BG, foreground=COLOR_TEXT, font=base_font)
    style.configure("TFrame", background=COLOR_BG)
    style.configure("Card.TFrame", background=COLOR_SURFACE)

    # Notebook / tabs
    style.configure("TNotebook", background=COLOR_BG, borderwidth=0)
    style.configure(
        "TNotebook.Tab",
        padding=[18, 9],
        font=("Segoe UI", 10, "bold"),
        background="#e2e8f0",
        foreground=COLOR_MUTED,
        borderwidth=0,
    )
    style.map(
        "TNotebook.Tab",
        background=[("selected", COLOR_SURFACE)],
        foreground=[("selected", COLOR_ACCENT)],
    )

    # Section "cards" (LabelFrame)
    style.configure(
        "TLabelframe",
        background=COLOR_SURFACE,
        bordercolor=COLOR_BORDER,
        relief="solid",
        borderwidth=1,
        padding=12,
    )
    style.configure(
        "TLabelframe.Label",
        background=COLOR_SURFACE,
        font=("Segoe UI", 10, "bold"),
        foreground=COLOR_ACCENT,
    )
    
    style.configure("TLabel", background=COLOR_SURFACE, foreground=COLOR_TEXT)
    style.configure("FormLabel.TLabel", background=COLOR_SURFACE, foreground=COLOR_MUTED,
                    font=("Segoe UI", 10, "bold"))
    style.configure("Hint.TLabel", background=COLOR_SURFACE, foreground=COLOR_MUTED,
                     font=("Segoe UI", 10))
    style.configure("OnBg.TLabel", background=COLOR_BG, foreground=COLOR_TEXT)

    # Inputs
    style.configure("TEntry", padding=8, fieldbackground="white", bordercolor=COLOR_BORDER)
    style.map("TEntry", bordercolor=[("focus", COLOR_ACCENT)])
    style.configure("TCombobox", padding=7, fieldbackground="white", bordercolor=COLOR_BORDER)
    style.map("TCombobox", bordercolor=[("focus", COLOR_ACCENT)],
              fieldbackground=[("readonly", "white")], foreground=[("readonly", COLOR_TEXT)])
    style.configure("TSpinbox", padding=4)
    style.configure("TCheckbutton", background=COLOR_SURFACE)

    # Buttons
    style.configure("TButton", padding=[12, 8], font=("Segoe UI", 10), relief="flat")
    style.map("TButton", background=[("active", "#e2e8f0")])

    style.configure("Accent.TButton", background=COLOR_ACCENT, foreground="white",
                     padding=[14, 9], font=("Segoe UI", 9, "bold"), borderwidth=0)
    style.map(
        "Accent.TButton",
        background=[("active", COLOR_ACCENT_DARK), ("disabled", "#a9c2f5")],
    )

    style.configure("Preview.TButton", background="#2563eb", foreground="white",
                    padding=[12, 8], font=("Segoe UI", 9, "bold"), borderwidth=0)
    style.map("Preview.TButton", background=[("active", "#1d4ed8")])

    style.configure("Danger.TButton", background=COLOR_DANGER, foreground="white",
                     padding=[12, 8], font=("Segoe UI", 9, "bold"), borderwidth=0,
                     focuscolor=COLOR_DANGER)
    style.map("Danger.TButton", background=[("active", COLOR_DANGER_DARK)])

    style.configure("Ghost.TButton", background=COLOR_SURFACE, foreground=COLOR_TEXT,
                     padding=[12, 8], font=("Segoe UI", 10))
    style.map("Ghost.TButton", background=[("active", "#f1f5f9")])

    # Treeview (tables)
    style.configure(
        "Treeview",
        rowheight=36,
        font=("Segoe UI", 10),
        background="white",
        fieldbackground="white",
        bordercolor=COLOR_BORDER,
        borderwidth=1,
    )
    style.configure(
        "Treeview.Heading",
        font=("Segoe UI", 9, "bold"),
        background="#f1f5f9",
        foreground=COLOR_TEXT,
        relief="flat",
    )
    style.map("Treeview", background=[("selected", COLOR_ACCENT_SOFT)],
               foreground=[("selected", COLOR_TEXT)])

    style.configure("Step.TButton", background="#edf3fa", foreground=COLOR_ACCENT,
                    padding=[12, 8], font=("Segoe UI", 10, "bold"), borderwidth=0)
    style.map("Step.TButton", background=[("active", "#dce8f5")])
    style.configure("Quantity.TLabel", background=COLOR_SURFACE, foreground=COLOR_ACCENT,
                    font=("Segoe UI", 13, "bold"))
    style.configure("TSeparator", background=COLOR_BORDER)
    style.configure("TScrollbar", troughcolor="#e2e8f0", background="#94a3b8",
                    bordercolor="#e2e8f0", arrowcolor=COLOR_ACCENT)
    style.map("TScrollbar", background=[("active", "#64748b")])

    return style