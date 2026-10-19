#!/usr/bin/env python3
"""
EReseta - Local Edition (Modern + Editable Template)
A standalone, no-login desktop app for creating and printing prescriptions.
Everything (patients, medicines, physicians, prescription history, template
layout) is stored locally in a SQLite database file next to this script.

Run with:  python ereseta_local.pyz

Requires: reportlab  (pip install reportlab)
Optional: openpyxl (for Excel medicine/barangay import)
Optional: Pillow (for the draggable logo/signature preview images)
Tkinter ships with standard Python on Windows/Mac; on Linux you may need
to install it separately (e.g. `sudo apt install python3-tk`).

This file is now just a thin launcher — all real logic lives in the
`ereseta_local` package next to it (config, database, pdf_generator,
fuzzy, widgets, theme, template_editor, app).
"""

from ereseta_local.app import EresetaApp
from ereseta_local.database import init_db


def main():
    init_db()
    app = EresetaApp()
    app.mainloop()


if __name__ == "__main__":
    main()
