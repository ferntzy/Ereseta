"""
Main application window: the "New Prescription" and "History" tabs, plus
wiring for the Template Editor tab.
"""

from __future__ import annotations

import datetime
import os
import shutil
import sys
import uuid
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Any

from . import theme
from .formatting import format_quantity
from .config import ASSETS_DIR, CIVIL_STATUS_OPTIONS, SEX_OPTIONS
from .database import (
    add_barangay,
    bulk_import_barangays,
    bulk_import_medicines,
    ensure_dr_prefix,
    find_or_create_medicine,
    find_or_create_patient,
    find_or_create_physician,
    full_name,
    get_all_barangays,
    get_all_medicines,
    get_all_patients,
    get_all_physicians,
    get_history,
    get_prescription_full,
    parse_birthday,
    set_setting,
    save_prescription,
)
from .pdf_generator import generate_pdf, prescription_pdf_bytes, open_file
from .prescription_preview import PrescriptionPreview
from .template_editor import TemplateEditor
from .opd_editor import OPDEditor
from .opd_layout_editor import OPDLayoutEditor
from .opd_database import unified_history, export_opd
from .widgets import AutocompleteCombobox, DateEntry

PrescriptionItem = dict[str, str]


class EresetaApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("EReseta \u2013 Local")
        icon_root = getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(__file__)))
        icon_path = os.path.join(icon_root, "assets", "ereseta.ico")
        if os.path.isfile(icon_path):
            self.iconbitmap(icon_path)
        self.geometry("1080x820")
        self.minsize(860, 660)
        self.resizable(True, True)

        # Modern-ish styling (colors + ttk theme live in ereseta_local.theme
        # so the Template Editor tab can share the same palette).
        self.style = theme.configure_styles(self)
        self._page_canvases: dict[str, tk.Canvas] = {}
        self._wheel_target = None
        self._wheel_remainder = 0.0
        self._wheel_tag = f"EResetaWheel{id(self)}"
        for sequence in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.bind_class(self._wheel_tag, sequence, self._scroll_active_page)

        self.patients_cache: dict[str, dict[str, Any]] = {}
        self.physicians_cache: dict[str, dict[str, Any]] = {}
        self.medicines_cache: dict[str, dict[str, Any]] = {}
        self.items: list[PrescriptionItem] = []
        self._editing_item = None
        self._removed_items = []
        self.workflow_status = tk.StringVar(value="Start by choosing a saved patient or entering a new patient below.")

        self._build_ui()
        self._refresh_caches()
        self.protocol("WM_DELETE_WINDOW", self._confirm_exit)
        self._bind_scroll_widgets(self)
        self.bind("<Map>", lambda event: self._bind_scroll_widgets(event.widget), add="+")

    def _build_ui(self) -> None:
        # Header bar
        header = tk.Frame(self, bg=theme.COLOR_ACCENT, height=62)
        header.pack(fill="x")
        header.pack_propagate(False)

        title_box = tk.Frame(header, bg=theme.COLOR_ACCENT)
        title_box.pack(side="left", padx=18, pady=6)
        tk.Label(title_box, text="\U0001F489  EReseta", font=("Segoe UI", 16, "bold"),
                 fg="white", bg=theme.COLOR_ACCENT).pack(anchor="w")
        tk.Label(title_box, text="Prescriptions & outpatient records", font=("Segoe UI", 9),
                 fg="#dbe6ff", bg=theme.COLOR_ACCENT).pack(anchor="w")

        tk.Label(header, text="Leyte Baptist Hospital", font=("Segoe UI", 9),
                 fg="#dbe6ff", bg=theme.COLOR_ACCENT).pack(side="right", padx=18)

        nb = self.notebook = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=12, pady=12)

        self.new_rx_tab = ttk.Frame(nb)
        self.opd_tab = ttk.Frame(nb)
        self.history_tab = ttk.Frame(nb)
        self.template_tab = ttk.Frame(nb)
        nb.add(self.new_rx_tab, text="  \U0001F4DD  New Prescription  ")
        nb.add(self.opd_tab, text="  OPD record  ")
        nb.add(self.history_tab, text="  History  ")
        nb.add(self.template_tab, text="  Layouts  ")

        navigation = ttk.Frame(self.new_rx_tab, padding=(10, 8), style="Card.TFrame")
        navigation.grid(row=0, column=0, columnspan=2, sticky="ew")
        for label, attr in [("1  Patient", "p_picker"), ("2  Doctor", "ph_name"), ("3  Medicines", "m_name"), ("4  Notes & date", "notes_entry")]:
            ttk.Button(navigation, text=label, style="Step.TButton", command=lambda name=attr:self._focus_field(getattr(self,name))).pack(side="left", padx=(0,6))
        ttk.Button(navigation, text="How to use", command=self._show_help).pack(side="right")
        footer = ttk.Frame(self.new_rx_tab, padding=10, style="Card.TFrame")
        footer.grid(row=2, column=0, columnspan=2, sticky="ew")
        ttk.Label(footer,textvariable=self.workflow_status,style="Hint.TLabel",wraplength=400).pack(side="left",fill="x",expand=True)
        ttk.Button(footer,text="Start over",command=self._confirm_clear_form,style="Ghost.TButton").pack(side="left",padx=8)
        ttk.Button(footer,text="Review & save",command=self._open_pdf_editor,style="Accent.TButton").pack(side="right")
        new_rx_content = self._make_scrollable_page(self.new_rx_tab)
        history_content = self._make_scrollable_page(self.history_tab)
        template_content = self._make_scrollable_page(self.template_tab)

        self._build_new_rx_tab(new_rx_content)
        self._build_history_tab(history_content)
        self.layout_tabs=ttk.Notebook(template_content)
        self.layout_tabs.pack(fill="both",expand=True,padx=8,pady=8)
        prescription_layout_panel=ttk.Frame(self.layout_tabs)
        self.opd_layout_panel=ttk.Frame(self.layout_tabs)
        self.layout_tabs.add(prescription_layout_panel,text="Prescription layout")
        self.layout_tabs.add(self.opd_layout_panel,text="OPD sheet layout")
        self.template_editor = TemplateEditor(prescription_layout_panel, self)
        self.template_editor.pack(fill="both", expand=True)
        opd_content = self._make_scrollable_page(self.opd_tab)
        self.opd_editor = OPDEditor(opd_content, self)
        self.opd_editor.pack(fill="both", expand=True)
        self.opd_layout_editor=OPDLayoutEditor(self.opd_layout_panel,self)
        self.opd_layout_editor.pack(fill="both",expand=True)
        opd_navigation = ttk.Frame(self.opd_tab, padding=(10,8), style="Card.TFrame")
        opd_navigation.grid(row=0,column=0,columnspan=2,sticky="ew")
        ttk.Button(opd_navigation,text="1  Patient & doctor",style="Step.TButton",command=lambda:self.opd_editor.focus_field(self.opd_editor.fields["first_name"])).pack(side="left",padx=(0,6))
        def focus_opd_notes():
            current=self.opd_editor.soap_tabs.select()
            key=next(k for k,panel in self.opd_editor.soap_panels.items() if str(panel)==current)
            self.opd_editor.focus_field(self.opd_editor.soap[key])
        ttk.Button(opd_navigation,text="2  SOAP notes",style="Step.TButton",command=focus_opd_notes).pack(side="left")
        ttk.Button(opd_navigation,text="Paper & layout",command=self.opd_editor.open_layout).pack(side="right")
        opd_footer = ttk.Frame(self.opd_tab, padding=10, style="Card.TFrame")
        opd_footer.grid(row=2,column=0,columnspan=2,sticky="ew")
        ttk.Label(opd_footer,textvariable=self.opd_editor.status,style="Hint.TLabel",wraplength=400).pack(side="left",fill="x",expand=True)
        ttk.Button(opd_footer,text="Start over",command=self.opd_editor.clear,style="Ghost.TButton").pack(side="left",padx=8)
        ttk.Button(opd_footer,text="Review & save OPD",command=self.opd_editor.preview,style="Accent.TButton").pack(side="right")

    def _make_scrollable_page(self, page: ttk.Frame) -> ttk.Frame:
        """Create an independent vertical scroll area for one notebook page."""
        scroll_row = 1 if page in (self.new_rx_tab, self.opd_tab) else 0
        page.grid_rowconfigure(scroll_row, weight=1)
        page.grid_columnconfigure(0, weight=1)
        canvas = tk.Canvas(page, bg=theme.COLOR_BG, highlightthickness=0, yscrollincrement=16)
        self._page_canvases[str(page)] = canvas
        scrollbar = ttk.Scrollbar(page, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.grid(row=scroll_row, column=0, sticky="nsew")
        scrollbar.grid(row=scroll_row, column=1, sticky="ns")

        content = ttk.Frame(canvas, style="Card.TFrame")
        window_id = canvas.create_window((0, 0), window=content, anchor="nw")

        content.bind("<Configure>", lambda event: canvas.configure(scrollregion=canvas.bbox("all")))
        def resize_page(event):
            options = {"width": event.width}
            if page in (self.template_tab, self.history_tab):
                # Keep page actions visible while settings or history rows scroll.
                options["height"] = max(450, event.height)
            canvas.itemconfigure(window_id, **options)
        canvas.bind("<Configure>", resize_page)

        return content

    def _bind_scroll_widgets(self, widget: tk.Misc) -> None:
        """Route wheel events before widget class bindings can change field values."""
        if not isinstance(widget, tk.Misc) or widget.winfo_toplevel() is not self:
            return  # Native Tcl popups and dialogs retain their own scrolling.
        tags = widget.bindtags()
        if self._wheel_tag not in tags:
            widget.bindtags((tags[0], self._wheel_tag, *tags[1:]))
        for child in widget.winfo_children():
            self._bind_scroll_widgets(child)

    def _scroll_active_page(self, event: tk.Event) -> str:
        # Resolve the target from this event, never from the last hovered tab.
        targets = []
        widget = event.widget
        while widget is not None:
            if isinstance(widget, (ttk.Treeview, tk.Text, tk.Listbox)):
                targets.append(widget)
            elif isinstance(widget, tk.Canvas) and widget.cget("scrollregion"):
                targets.append(widget)
            widget = widget.master

        selected = self.notebook.select()
        fallback = self._page_canvases.get(selected)
        if fallback is not None and fallback not in targets:
            targets.append(fallback)
        # Blank areas in History and Template Editor still scroll useful content.
        if selected == str(self.history_tab):
            targets.append(self.history_tree)
        elif selected == str(self.template_tab):
            targets.append(self.template_editor.settings_canvas)

        number = getattr(event, "num", None)
        delta = -120 if number == 5 else 120 if number == 4 else getattr(event, "delta", 0)
        if not delta:
            return "break"
        direction = -1 if delta > 0 else 1
        for target in dict.fromkeys(targets):
            if not target.winfo_ismapped():
                continue
            start, end = target.yview()
            if (direction < 0 and start <= 0) or (direction > 0 and end >= 1):
                continue
            # Accumulate small touchpad deltas instead of rounding them to zero.
            if target is not self._wheel_target or self._wheel_remainder * direction < 0:
                self._wheel_remainder = 0.0
            self._wheel_target = target
            self._wheel_remainder += -delta / 120 * 3
            units = int(self._wheel_remainder)
            self._wheel_remainder -= units
            if units:
                target.yview_scroll(units, "units")
            break
        else:
            self._wheel_remainder = 0.0
        # Prevent native controls and ancestor pages from scrolling a second time.
        return "break"

    def _build_new_rx_tab(self, parent: ttk.Widget) -> None:
        layout = ttk.Frame(parent, style="Card.TFrame")
        layout.pack(fill="both", expand=True, padx=8, pady=8)
        layout.columnconfigure(0, weight=3)
        layout.columnconfigure(1, weight=0)
        left = ttk.Frame(layout, style="Card.TFrame")
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        right = ttk.Frame(layout, style="Card.TFrame", padding=12)
        right.grid(row=0, column=1, sticky="nsew")
        self.prescription_preview_panel = right
        parent = left

        intro = ttk.Frame(parent, style="Card.TFrame", padding=(12, 10))
        intro.pack(fill="x", padx=8, pady=(8, 6))
        ttk.Label(intro, text="Create a prescription", font=("Segoe UI", 16, "bold"),
                  foreground=theme.COLOR_ACCENT).pack(anchor="w")
        ttk.Label(intro, text="Complete the steps below, then review the printable copy. Fields marked * are required.",
                  wraplength=720,
                  style="Hint.TLabel").pack(anchor="w", pady=(2, 0))

        def section(title):
            frame = ttk.LabelFrame(parent, text=title)
            frame.pack(fill="x", padx=8, pady=8)
            for column in range(3):
                frame.columnconfigure(column, weight=1, uniform="fields")
            return frame

        def field(frame, label, widget, row, column, span=1):
            ttk.Label(frame, text=label, style="FormLabel.TLabel").grid(
                row=row, column=column, columnspan=span, sticky="w", padx=6, pady=(8, 3))
            widget.grid(row=row + 1, column=column, columnspan=span, sticky="ew", padx=6, pady=(0, 6))
            return widget

        pf = section("  1  Patient details  ")
        self.p_picker = field(pf, "Find a saved patient (optional)", AutocompleteCombobox(pf, width=24, auto_dropdown=True), 0, 0, 2)
        self.p_picker.bind("<<ComboboxSelected>>", self._on_patient_picked)
        ttk.Button(pf, text="Save patient only", command=self._save_patient_record).grid(row=1, column=2, padx=6, sticky="e")
        self.p_first = field(pf, "First name *", ttk.Entry(pf, width=16), 2, 0)
        self.p_middle = field(pf, "Middle name", ttk.Entry(pf, width=16), 2, 1)
        self.p_last = field(pf, "Last name *", ttk.Entry(pf, width=16), 2, 2)
        self.p_age = field(pf, "Age in years *", ttk.Entry(pf, width=10), 4, 0)
        self.p_sex = field(pf, "Sex", ttk.Combobox(pf, width=12, values=SEX_OPTIONS, state="readonly"), 4, 1)
        self.p_civil = field(pf, "Civil status", ttk.Combobox(pf, width=12, values=CIVIL_STATUS_OPTIONS, state="readonly"), 4, 2)
        self.civil_other_frame = ttk.Frame(pf, style="Card.TFrame")
        self.civil_other_frame.grid(row=6, column=0, columnspan=3, sticky="ew", padx=6, pady=6)
        ttk.Label(self.civil_other_frame, text="Please specify civil status *", style="FormLabel.TLabel").pack(anchor="w")
        self.p_civil_other = ttk.Entry(self.civil_other_frame)
        self.p_civil_other.pack(fill="x", pady=(3, 0))
        self.civil_other_frame.grid_remove()
        self.p_civil.bind("<<ComboboxSelected>>", self._civil_status_changed)
        self.p_address = field(pf, "Address / barangay", AutocompleteCombobox(pf, width=24, auto_dropdown=True), 8, 0, 3)

        phf = section("  2  Doctor & signature  ")
        self.ph_name = field(phf, "Doctor name *", AutocompleteCombobox(phf, width=20, auto_dropdown=True), 0, 0)
        self.ph_name.bind("<<ComboboxSelected>>", self._on_physician_picked)
        self.ph_license = field(phf, "License number", ttk.Entry(phf, width=16), 0, 1)
        self.ph_ptr = field(phf, "PTR number", ttk.Entry(phf, width=16), 0, 2)
        self.ph_signature = tk.StringVar(value="")
        self.signature_status = tk.StringVar(value="No signature assigned")
        self.ph_signature.trace_add("write", lambda *_: self.signature_status.set(
            "Signature assigned" if self.ph_signature.get() else "No signature assigned"))
        signature_bar = ttk.Frame(phf, style="Card.TFrame")
        signature_bar.grid(row=2, column=0, columnspan=3, sticky="ew", padx=6, pady=(8, 4))
        ttk.Label(signature_bar, textvariable=self.signature_status, style="Hint.TLabel").pack(side="left", padx=(0, 12))
        ttk.Button(signature_bar, text="Choose / replace signature", command=self._choose_signature).pack(side="left")
        ttk.Button(signature_bar, text="Remove", command=lambda: self.ph_signature.set(""), style="Ghost.TButton").pack(side="left", padx=6)
        ttk.Button(signature_bar, text="Save doctor only", command=self._save_physician_record).pack(side="right")
        ttk.Label(phf, text="Choose a saved doctor to fill in their details and signature automatically.", style="Hint.TLabel").grid(row=3, column=0, columnspan=3, sticky="w", padx=6, pady=(2, 4))
        self.ph_name.bind("<KeyRelease>", self._on_physician_name_edited, add="+")

        mf = section("  3  Add medicines  ")
        # self.m_name = field(mf, "Medicine name *", AutocompleteCombobox(mf, width=24, auto_dropdown=True), 0, 0)
        self.m_name = field(mf, "Medicine name *", AutocompleteCombobox(mf, width=24, auto_dropdown=True), 0, 0, 2)
        self.m_name.bind("<<ComboboxSelected>>", self._on_medicine_picked)
        # self.m_dosage = field(mf, "Dosage", ttk.Entry(mf, width=14), 0, 1)
        # Dosage temporarily disabled. Original code retained below.
        quantity_field = field(mf, "Quantity (optional)", ttk.Frame(mf, style="Card.TFrame"), 0, 2)
        ttk.Label(quantity_field, text="#", style="Quantity.TLabel").pack(side="left", padx=(0, 4))
        quantity_value = tk.StringVar()
        quantity_value.trace_add("write", lambda *_: quantity_value.set(quantity_value.get().lstrip("# \t\r\n")))
        self.m_qty = ttk.Entry(quantity_field, width=10, textvariable=quantity_value)
        self.m_qty.pack(side="left", fill="x", expand=True)
        ttk.Label(mf, text="Type to search, or enter a new medicine.", style="Hint.TLabel", wraplength=420).grid(row=2, column=0, columnspan=2, sticky="w", padx=6, pady=(0, 4))
        ttk.Label(mf, text="Leave blank to write the number on paper.", style="Hint.TLabel", wraplength=220).grid(
            row=2, column=2, sticky="w", padx=6, pady=(0, 4))
        self.m_instructions = field(mf, "How the patient should take it", ttk.Entry(mf, width=24), 3, 0, 2)
        self.add_medicine_button = ttk.Button(mf, text="Add to prescription", command=self._add_item, style="Accent.TButton")
        self.add_medicine_button.grid(row=4, column=2, padx=6, pady=(0,6), sticky="e")
        self.cancel_medicine_button = ttk.Button(mf,text="Cancel changes",command=self._cancel_item_edit)
        self.cancel_medicine_button.grid(row=5,column=2,sticky="e",padx=6)
        self.cancel_medicine_button.grid_remove()
        self.m_instructions.bind("<Return>", lambda event: self._add_item())
        imports = ttk.Frame(mf, style="Card.TFrame")
        imports.grid(row=7, column=0, columnspan=3, sticky="w", padx=6, pady=(8, 0))
        ttk.Button(imports, text="Import medicines", style="Ghost.TButton", command=self._import_medicines).pack(side="left")
        ttk.Button(imports, text="Import barangays", style="Ghost.TButton", command=self._import_barangays).pack(side="left", padx=8)

        imports.grid_remove()
        ttk.Button(mf,text="Set up medicine / address lists",style="Ghost.TButton",
            command=lambda: imports.grid_remove() if imports.winfo_ismapped() else imports.grid()).grid(row=6,column=0,columnspan=3,sticky="w",padx=6,pady=6)

        # --- Items list ---
        lf = ttk.LabelFrame(parent, text="  Medicines on this prescription  ")
        lf.pack(fill="both", expand=True, padx=8, pady=6)

        self.medicine_status = tk.StringVar(value="No medicines added yet. Fill in the medicine above, then click Add to prescription.")
        ttk.Label(lf,textvariable=self.medicine_status,style="Hint.TLabel",wraplength=650).pack(anchor="w",pady=(0,6))
        tree_row = ttk.Frame(lf, style="Card.TFrame")
        tree_row.pack(fill="both", expand=True)

        # cols = ("medicine", "dosage", "qty", "instructions")
        cols = ("medicine", "qty", "instructions")
        self.items_tree = ttk.Treeview(tree_row, columns=cols, show="headings", height=6)
        for c, label, w in [
            ("medicine", "Medicine", 190),
            # ("dosage", "Dosage", 100),

            ("qty", "Quantity", 100),
            ("instructions", "Instructions", 290),
        ]:
            self.items_tree.heading(c, text=label)
            self.items_tree.column(c, width=w)
        self.items_tree.pack(fill="both", expand=True, side="left", pady=(4, 0))
        self.items_tree.bind("<Double-1>", lambda event: self._edit_item())
        self.items_tree.tag_configure("odd", background="#f2f6fb")
        self.items_tree.column("qty", anchor="center", stretch=False, minwidth=100)

        sb = ttk.Scrollbar(tree_row, orient="vertical", command=self.items_tree.yview)
        sb.pack(side="left", fill="y", pady=(4, 0))
        self.items_tree.configure(yscrollcommand=sb.set)

        item_actions = ttk.Frame(lf, style="Card.TFrame")
        item_actions.pack(side="top", anchor="w", fill="x", pady=(8, 0))
        self.edit_medicine_button = ttk.Button(item_actions, text="Edit selected", command=self._edit_item)
        self.edit_medicine_button.pack(side="left")
        self.remove_medicine_button = ttk.Button(item_actions, text="Remove selected", style="Ghost.TButton", command=self._remove_item)
        self.remove_medicine_button.pack(side="left", padx=(6, 0))
        self.items_tree.bind("<<TreeviewSelect>>", self._update_medicine_actions)
        self._update_medicine_actions()

        self.undo_medicine_button = ttk.Button(item_actions,text="Undo removal",command=self._undo_remove,style="Ghost.TButton")
        self.undo_medicine_button.pack(side="left",padx=6)
        self.undo_medicine_button.state(["disabled"])
        bottom = section("  4  Notes & prescription date  ")
        self.notes_entry = field(bottom, "Notes (optional, printed at bottom left)", ttk.Entry(bottom, width=24), 0, 0, 2)
        self.rx_date = field(bottom, "Prescription date", DateEntry(bottom, default=datetime.date.today(), width=12), 0, 2)
        ttk.Label(bottom,text="Ready? Click Review & save below to check the printable prescription before saving.",style="Hint.TLabel",wraplength=650).grid(row=2,column=0,columnspan=3,sticky="w",padx=6,pady=8)

        self._build_live_preview(right)
        # The exact PDF is available on demand; avoid showing an approximate
        # duplicate preview during normal prescription entry.
        right.grid_remove()

    def _open_pdf_editor(self) -> None:
        draft = self._collect_draft()
        if draft is None:
            return
        try:
            pdf = prescription_pdf_bytes(draft["patient"], draft["physician"], draft["items"],
                notes=draft["notes"], date_issued=draft["date"], template=draft["template"])
            self.draft_preview = PrescriptionPreview(self, pdf, lambda: self._save_draft(draft))
        except Exception as exc:
            messagebox.showerror("Preview failed", str(exc))

    def _build_live_preview(self, parent: ttk.Frame) -> None:
        ttk.Label(parent, text="Prescription Preview", font=("Segoe UI", 12, "bold"),
                  foreground=theme.COLOR_ACCENT).pack(anchor="w")
        ttk.Label(parent, text="Live view of the prescription layout", style="Hint.TLabel").pack(
            anchor="w", pady=(2, 10)
        )
        self.preview_canvas = tk.Canvas(parent, bg="#eef2f7", highlightthickness=0)
        self.preview_canvas.pack(fill="both", expand=True)

        tracked_entries = [
            self.p_first, self.p_middle, self.p_last, self.p_age, self.p_picker, self.p_address,
            # self.ph_name, self.m_name, self.m_dosage, self.m_qty, self.m_instructions,
            self.ph_name, self.m_name, self.m_qty, self.m_instructions,
        ]
        for entry in tracked_entries:
            entry.bind("<KeyRelease>", lambda event: self._refresh_live_preview(), add="+")
        for variable in (self.rx_date._var,):
            variable.trace_add("write", lambda *_: self._refresh_live_preview())
        self.p_sex.bind("<<ComboboxSelected>>", lambda event: self._refresh_live_preview(), add="+")
        self.p_civil.bind("<<ComboboxSelected>>", lambda event: self._refresh_live_preview(), add="+")
        self._refresh_live_preview()

    def _refresh_live_preview(self) -> None:
        if not hasattr(self, "preview_canvas"):
            return
        self.preview_canvas.delete("all")
        width = max(self.preview_canvas.winfo_width(), 280)
        height = max(self.preview_canvas.winfo_height(), 420)
        paper_w = min(width - 24, 360)
        paper_h = min(height - 24, 500)
        x0 = (width - paper_w) / 2
        y0 = 12
        self.preview_canvas.create_rectangle(x0, y0, x0 + paper_w, y0 + paper_h,
                                             fill="white", outline="#cbd5e1")
        pad = 18
        x = x0 + pad
        y = y0 + pad
        center = x0 + paper_w / 2
        self.preview_canvas.create_text(center, y, text="LEYTE BAPTIST HOSPITAL", font=("Segoe UI", 9, "bold"),
                                        fill=theme.COLOR_ACCENT)
        y += 15
        self.preview_canvas.create_text(center, y, text="Prescriptions & outpatient records", font=("Segoe UI", 7), fill="#64748b")
        y += 16
        self.preview_canvas.create_line(x, y, x0 + paper_w - pad, y, fill="#cbd5e1")
        y += 18

        patient_name = " ".join(value for value in (self.p_first.get(), self.p_middle.get(), self.p_last.get()) if value).strip()
        patient_name = patient_name or "Patient name"
        self.preview_canvas.create_text(x, y, text=f"Patient: {patient_name}", anchor="w", font=("Segoe UI", 8, "bold"), fill="#0f172a")
        y += 15
        age_text = self.p_age.get().strip() or "--"
        sex = self.p_sex.get() or "--"
        self.preview_canvas.create_text(x, y, text=f"Age/Sex: {age_text} / {sex}", anchor="w", font=("Segoe UI", 7), fill="#475569")
        y += 15
        address = self.p_address.get() or "Address"
        self.preview_canvas.create_text(x, y, text=f"Address: {address}", anchor="w", font=("Segoe UI", 7), fill="#475569")
        y += 25
        self.preview_canvas.create_text(x, y, text="Rx", anchor="w", font=("Georgia", 22, "italic"), fill=theme.COLOR_ACCENT)
        y += 30

        if not self.items:
            self.preview_canvas.create_text(x, y, text="Medicines will appear here", anchor="w", font=("Segoe UI", 8, "italic"), fill="#94a3b8")
            y += 22
        for item in self.items:
            medicine = item["name"] or "Medicine"
            # dosage = item["dosage"]

            # label = f"{medicine} {dosage}".strip()
            label = medicine
            self.preview_canvas.create_text(x, y, text=label, anchor="w", width=paper_w - 2 * pad,
                                            font=("Segoe UI", 8, "bold"), fill="#0f172a")
            y += 14
            if item["instructions"]:
                self.preview_canvas.create_text(x + 8, y, text=item["instructions"], anchor="w", width=paper_w - 2 * pad - 8,
                                                font=("Segoe UI", 7), fill="#475569")
                y += 13
            self.preview_canvas.create_text(x + paper_w - 2 * pad, y - 14, text=format_quantity(item["quantity"]),
                                            anchor="e", font=("Segoe UI", 7, "bold"), fill="#475569")
            y += 14
            if y > y0 + paper_h - 70:
                break

        self.preview_canvas.create_line(x + paper_w - 150, y0 + paper_h - 50, x0 + paper_w - pad, y0 + paper_h - 50, fill="#64748b")
        physician = self.ph_name.get().strip() or "Physician name"
        license_no = self.ph_license.get().strip() or "--"
        ptr_no = self.ph_ptr.get().strip() or "--"
        self.preview_canvas.create_text(x + paper_w - 75, y0 + paper_h - 37, text=physician,
                        font=("Segoe UI", 8), fill="#0f172a")
        self.preview_canvas.create_text(x + paper_w - 75, y0 + paper_h - 23,
                        text=f"Lic #: {license_no}   PTR: {ptr_no}",
                        font=("Segoe UI", 7), fill="#64748b")

    def _build_history_tab(self, parent: ttk.Widget) -> None:
        top = ttk.Frame(parent, style="Card.TFrame", padding=10)
        top.pack(fill="x", padx=8, pady=8)
        ttk.Label(top, text="History", font=("Segoe UI", 16, "bold"), style="Hint.TLabel").pack(anchor="w")
        ttk.Label(top, text="Search by patient, doctor, or date. Select a result to open or copy it.", style="Hint.TLabel").pack(anchor="w", pady=(4, 0))
        filters = ttk.Frame(top, style="Card.TFrame"); filters.pack(fill="x", pady=10)
        for column in range(4): filters.columnconfigure(column, weight=1)
        self.history_patient = tk.StringVar()
        self.history_doctor = tk.StringVar()
        self.history_type = tk.StringVar(value="All")
        self.history_hospital = tk.StringVar()
        self._history_job = None
        for column, label, variable in [(0,"Patient name",self.history_patient),(1,"Doctor name",self.history_doctor)]:
            ttk.Label(filters,text=label,style="FormLabel.TLabel").grid(row=0,column=column,sticky="w",padx=4)
            entry=ttk.Entry(filters,textvariable=variable,width=18)
            entry.grid(row=1,column=column,sticky="ew",padx=4)
            entry.bind("<Return>",lambda e:self._refresh_history(show_errors=True))
        # Keep doctor/date filters available without crowding the default history view.
        for widget in filters.grid_slaves(column=1):widget.grid_remove()
        ttk.Label(filters,text="Record type",style="FormLabel.TLabel").grid(row=0,column=1,sticky="w",padx=4)
        ttk.Combobox(filters,textvariable=self.history_type,values=["All","Prescription","OPD"],state="readonly",width=18).grid(row=1,column=1,sticky="ew",padx=4)
        advanced=ttk.Frame(top,style="Card.TFrame")
        advanced.pack(fill="x",pady=(0,10))
        for col in range(4):advanced.columnconfigure(col,weight=1)
        ttk.Label(advanced,text="Doctor",style="FormLabel.TLabel").grid(row=0,column=0,sticky="w",padx=4)
        ttk.Entry(advanced,textvariable=self.history_doctor,width=16).grid(row=1,column=0,sticky="ew",padx=4)
        ttk.Label(advanced,text="From date",style="FormLabel.TLabel").grid(row=0,column=1,sticky="w",padx=4)
        ttk.Label(advanced,text="To date",style="FormLabel.TLabel").grid(row=0,column=2,sticky="w",padx=4)
        self.history_from=DateEntry(advanced,width=12);self.history_from.clear();self.history_from.grid(row=1,column=1,sticky="ew",padx=4)
        self.history_to=DateEntry(advanced,width=12);self.history_to.clear();self.history_to.grid(row=1,column=2,sticky="ew",padx=4)
        ttk.Label(advanced,text="Hospital no. (OPD)",style="FormLabel.TLabel").grid(row=0,column=3,sticky="w",padx=4)
        ttk.Entry(advanced,textvariable=self.history_hospital,width=16).grid(row=1,column=3,sticky="ew",padx=4)
        advanced.pack_forget()
        def toggle_filters():
            if advanced.winfo_manager():
                advanced.pack_forget();filter_toggle.configure(text="More filters")
            else:
                advanced.pack(fill="x",pady=(0,10),after=filters);filter_toggle.configure(text="Hide filters")
        filter_toggle=ttk.Button(filters,text="More filters",command=toggle_filters)
        filter_toggle.grid(row=1,column=2,sticky="w",padx=8)
        actions=ttk.Frame(top,style="Card.TFrame");actions.pack(fill="x")
        ttk.Button(actions,text="Search",command=lambda:self._refresh_history(show_errors=True)).pack(side="left")
        ttk.Button(actions,text="Clear filters",command=self._clear_history_filters).pack(side="left",padx=6)
        ttk.Button(actions,text="Reuse as new draft",command=self._reuse_prescription,style="Accent.TButton").pack(side="right")
        ttk.Button(actions,text="Open selected PDF",command=self._open_selected_history_pdf).pack(side="right",padx=6)
        self.history_status=tk.StringVar()
        ttk.Label(top,textvariable=self.history_status,style="Hint.TLabel").pack(anchor="w",pady=(8,0))
        for variable in (self.history_patient,self.history_doctor,self.history_from._var,self.history_to._var,self.history_type,self.history_hospital):
            variable.trace_add("write",self._schedule_history_search)

        table_frame = ttk.LabelFrame(parent, text="  History  ")
        table_frame.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        cols = ("id", "type", "date", "patient", "physician", "hospital")
        self.history_tree = ttk.Treeview(table_frame, columns=cols, show="headings")
        for c, label, w in [
            ("id", "ID", 45),
            ("type", "Type", 95),
            ("date", "Date", 110),
            ("patient", "Patient", 200),
            ("physician", "Doctor", 160),
            ("hospital", "Hospital no.", 110),
        ]:
            self.history_tree.heading(c, text=label)
            self.history_tree.column(c, width=w)
        self.history_tree.pack(fill="both", expand=True, side="left", pady=4)
        hsb = ttk.Scrollbar(table_frame, orient="vertical", command=self.history_tree.yview)
        hsb.pack(side="left", fill="y", pady=4)
        self.history_tree.configure(yscrollcommand=hsb.set)
        self.history_tree.tag_configure("odd", background="#f7f9fc")
        self._refresh_history()

    def _read_age(self) -> int | None:
        value = self.p_age.get().strip()
        if not value.isascii() or not value.isdigit() or not 0 <= int(value) <= 130:
            messagebox.showwarning("Invalid age", "Enter age in whole years from 0 to 130.")
            self._focus_field(self.p_age)
            return None
        return int(value)

    def _on_physician_name_edited(self, event=None) -> None:
        ph = self.physicians_cache.get(self.ph_name.get())
        self.ph_signature.set((ph["signature_path"] or "") if ph else "")

    def _choose_signature(self) -> None:
        path = filedialog.askopenfilename(title="Choose doctor's e-signature", filetypes=[("Signature image", "*.png *.jpg *.jpeg *.bmp")])
        if not path:
            return
        try:
            from PIL import Image
            with Image.open(path) as img:
                img.verify()
            folder = os.path.join(ASSETS_DIR, "signatures")
            os.makedirs(folder, exist_ok=True)
            saved = os.path.join(folder, uuid.uuid4().hex + os.path.splitext(path)[1].lower())
            shutil.copy2(path, saved)
        except Exception as exc:
            messagebox.showerror("Signature image", f"Could not load signature: {exc}")
            return
        self.ph_signature.set(saved)

    def _refresh_caches(self) -> None:
        self.patients_cache = {full_name(p): p for p in get_all_patients()}
        self.p_picker.set_completion_list(sorted(self.patients_cache.keys()))

        self.physicians_cache = {p["name"]: p for p in get_all_physicians()}
        self.ph_name.set_completion_list(sorted(self.physicians_cache.keys()))

        meds = get_all_medicines()
        self.medicines_cache = {m["name"]: m for m in meds}
        self.m_name.set_completion_list(sorted(self.medicines_cache.keys()))

        self.p_address.set_completion_list(get_all_barangays())

    def _schedule_history_search(self, *_):
        if self._history_job:
            self.after_cancel(self._history_job)
        self._history_job=self.after(250,self._refresh_history)

    def _clear_history_filters(self):
        self.history_patient.set("");self.history_doctor.set("")
        self.history_from.clear();self.history_to.clear()
        self.history_type.set("All");self.history_hospital.set("")
        self._refresh_history()

    def _refresh_history(self, show_errors=False) -> None:
        if self._history_job:
            self.after_cancel(self._history_job)
            self._history_job=None
        start=end=None
        for field,label in [(self.history_from,"From"),(self.history_to,"To")]:
            if field.get() and parse_birthday(field.get()) is None:
                self.history_status.set(f"Enter a valid {label.lower()} date (MM/DD/YYYY), or leave it blank. Results have not changed.")
                if show_errors: messagebox.showwarning("Invalid date",self.history_status.get())
                return
        if self.history_from.get():start=parse_birthday(self.history_from.get()).isoformat()
        if self.history_to.get():end=parse_birthday(self.history_to.get()).isoformat()
        if start and end and start>end:
            self.history_status.set("From date must be on or before To date. Results have not changed.")
            if show_errors:messagebox.showwarning("Date range",self.history_status.get())
            return
        rows=unified_history(patient_query=self.history_patient.get(),physician_query=self.history_doctor.get(),date_from=start,date_to=end,kind=self.history_type.get(),hospital_query=self.history_hospital.get())
        for row in self.history_tree.get_children():self.history_tree.delete(row)
        for i,h in enumerate(rows):
            self.history_tree.insert("","end",iid=f"{h['kind']}:{h['id']}",values=(h["id"],h["kind"],h["date"],h["patient"],h["doctor"],h["hospital"]),tags=("odd",) if i%2 else ())
        active=[]
        if self.history_doctor.get():active.append("doctor: "+self.history_doctor.get())
        if start:active.append("from "+start)
        if end:active.append("to "+end)
        if self.history_hospital.get():active.append("hospital no.: "+self.history_hospital.get())
        self.history_status.set((f"{len(rows)} record(s) found." if rows else "No records match these filters.")+(" Filters: "+", ".join(active) if active else ""))

    def _reuse_prescription(self):
        selected=self.history_tree.selection()
        if not selected:
            messagebox.showinfo("Select a record","Select a record in History first.")
            return
        values=self.history_tree.item(selected[0],"values")
        if values[1]=="OPD":
            self.opd_editor.reuse_record(int(values[0]));return
        prescription_id=int(values[0])
        if self._has_draft():
            if not messagebox.askyesno("Replace current draft?","Load this prescription as a new draft? Unsaved form entries will be replaced."):
                return
        presc,patient,physician,items=get_prescription_full(prescription_id)
        self._clear_form()
        for field,value in [(self.p_first,patient["first_name"]),(self.p_middle,patient["middle_name"]),
                (self.p_last,patient["last_name"]),(self.p_age,patient["age"]),
                (self.ph_license,physician["license_no"]),(self.ph_ptr,physician["ptr_no"]),(self.notes_entry,presc["notes"])]:
            field.insert(0,"" if value is None else str(value))
        self.p_picker.set(full_name(patient));self.p_address.set(patient["address"] or "")
        self.p_sex.set(patient["sex"] or "");self._set_civil_status(patient["civil_status"] or "")
        self.ph_name.set(physician["name"]);self.ph_signature.set(physician["signature_path"] or "")
        self.rx_date.set(datetime.date.today())
        # self.items=[dict(name=row["medicine_name"],dosage=row["dosage"] or "",quantity=row["quantity"] or "",instructions=row["instructions"] or "") for row in items]
        self.items=[dict(name=row["medicine_name"],dosage="",quantity=row["quantity"] or "",instructions=row["instructions"] or "") for row in items]
        for item in self.items:
            # self.items_tree.insert("","end",values=(item["name"],item["dosage"],format_quantity(item["quantity"]),item["instructions"]))
            self.items_tree.insert("","end",values=(item["name"],format_quantity(item["quantity"]),item["instructions"]))
        self.notebook.select(self.new_rx_tab)
        self._page_canvases[str(self.new_rx_tab)].yview_moveto(0)
        self._refresh_items()
        self.workflow_status.set(f"Draft copied from prescription #{prescription_id}. Check all details before saving.")
        messagebox.showinfo("New draft ready",f"Copied prescription #{prescription_id} into a new draft dated today. Review all details, then preview or save.")

    def _civil_status_changed(self, event=None):
        if self.p_civil.get() == "Other":
            self.civil_other_frame.grid()
            if event is not None:
                self._focus_field(self.p_civil_other)
        else:
            self.civil_other_frame.grid_remove()

    def _set_civil_status(self, value):
        value = (value or "").strip()
        self.p_civil_other.delete(0, "end")
        if value and value not in CIVIL_STATUS_OPTIONS:
            self.p_civil.set("Other")
            self.p_civil_other.insert(0, value)
        else:
            self.p_civil.set(value)
        self._civil_status_changed()

    def _read_civil_status(self):
        value = self.p_civil.get().strip()
        if value == "Other":
            value = self.p_civil_other.get().strip()
            if not value:
                self._focus_field(self.p_civil_other)
                messagebox.showwarning("Civil status needed", "Please specify the civil status, or choose a different option.")
                return None
        return value

    def _on_patient_picked(self, event: tk.Event | None = None) -> None:
        key = self.p_picker.get()
        p = self.patients_cache.get(key)
        if not p:
            return
        self.p_first.delete(0, "end")
        self.p_first.insert(0, p["first_name"] or "")
        self.p_middle.delete(0, "end")
        self.p_middle.insert(0, p["middle_name"] or "")
        self.p_last.delete(0, "end")
        self.p_last.insert(0, p["last_name"] or "")
        age = p["age"]
        self.p_age.delete(0, "end")
        self.p_age.insert(0, str(age) if age is not None else "")
        if p["sex"] in SEX_OPTIONS:
            self.p_sex.set(p["sex"])
        self._set_civil_status(p["civil_status"] or "")
        self.p_address.set(p["address"] or "")

    def _on_physician_picked(self, event: tk.Event | None = None) -> None:
        key = self.ph_name.get()
        ph = self.physicians_cache.get(key)
        if not ph:
            return
        self.ph_license.delete(0, "end")
        self.ph_license.insert(0, ph["license_no"] or "")
        self.ph_ptr.delete(0, "end")
        self.ph_ptr.insert(0, ph["ptr_no"] or "")
        self.ph_signature.set(ph["signature_path"] or "")

    def _on_medicine_picked(self, event: tk.Event | None = None) -> None:
        # Instructions are entered by the user. Dosage is temporarily disabled.
        return

    def _save_patient_record(self) -> None:
        first = self.p_first.get().strip()
        last = self.p_last.get().strip()
        if not first or not last:
            messagebox.showwarning("Missing info", "Patient first and last name are required.")
            return

        middle = self.p_middle.get().strip()
        age = self._read_age()
        if age is None:
            return
        sex = self.p_sex.get().strip()
        civil = self._read_civil_status()
        if civil is None:
            return
        address = self.p_address.get().strip()

        patient_id = find_or_create_patient(first, middle, last, age, sex, address, civil)
        if address:
            add_barangay(address)
        self._refresh_caches()
        full = full_name({"first_name": first, "middle_name": middle, "last_name": last})
        self.p_picker.set(full)
        messagebox.showinfo("Patient saved", f"Patient record saved for {full} (ID: {patient_id}).")

    def _save_physician_record(self) -> None:
        name = self.ph_name.get().strip()
        if not name:
            messagebox.showwarning("Missing info", "Physician name is required.")
            return

        license_no = self.ph_license.get().strip()
        ptr_no = self.ph_ptr.get().strip()
        physician_id = find_or_create_physician(name, license_no, ptr_no, self.ph_signature.get())
        self._refresh_caches()
        self.ph_name.set(ensure_dr_prefix(name))
        messagebox.showinfo("Physician saved", f"Physician record saved for {name} (ID: {physician_id}).")

    def _import_medicines(self) -> None:
        file_path = filedialog.askopenfilename(
            title="Select medicine list (CSV or Excel)",
            filetypes=[
                ("CSV or Excel files", "*.csv *.xlsx *.xls"),
                ("CSV files", "*.csv"),
                ("Excel files", "*.xlsx *.xls"),
                ("All files", "*.*"),
            ],
        )
        if not file_path:
            return
        try:
            added, updated, skipped = bulk_import_medicines(file_path)
        except Exception as ex:
            messagebox.showerror("Import failed", str(ex))
            return
        self._refresh_caches()
        messagebox.showinfo(
            "Import complete",
            f"Added: {added}\nUpdated: {updated}\nSkipped (no name): {skipped}\n\n"
            f"Total medicines now in the list: {len(self.medicines_cache)}",
        )

    def _import_barangays(self) -> None:
        file_path = filedialog.askopenfilename(
            title="Select barangay list (CSV or Excel)",
            filetypes=[
                ("CSV or Excel files", "*.csv *.xlsx *.xls"),
                ("CSV files", "*.csv"),
                ("Excel files", "*.xlsx *.xls"),
                ("All files", "*.*"),
            ],
        )
        if not file_path:
            return
        try:
            added, skipped = bulk_import_barangays(file_path)
        except Exception as ex:
            messagebox.showerror("Import failed", str(ex))
            return
        self._refresh_caches()
        total = len(get_all_barangays())
        messagebox.showinfo(
            "Barangay import complete",
            f"Added: {added}\nSkipped (duplicate/empty): {skipped}\n\n"
            f"Total addresses/barangays in list: {total}",
        )

    def _update_medicine_actions(self, event=None):
        state = ["!disabled"] if self.items_tree.selection() else ["disabled"]
        self.edit_medicine_button.state(state)
        self.remove_medicine_button.state(state)

    def _refresh_items(self):
        for row in self.items_tree.get_children():self.items_tree.delete(row)
        for index, item in enumerate(self.items):
            # self.items_tree.insert("","end",values=(item["name"],item["dosage"],format_quantity(item["quantity"]),item["instructions"]), tags=("odd",) if index % 2 else ())
            self.items_tree.insert("","end",values=(item["name"],format_quantity(item["quantity"]),item["instructions"]), tags=("odd",) if index % 2 else ())
        self.medicine_status.set(f"{len(self.items)} medicine(s) added. Select a row to change or remove it." if self.items else "No medicines added yet. Fill in the medicine above, then click Add to prescription.")
        self._update_medicine_actions()
        self._refresh_live_preview()

    def _cancel_item_edit(self):
        self._editing_item=None
        self.m_name.set("")
        # for entry in (self.m_dosage,self.m_qty,self.m_instructions):entry.delete(0,"end")
        for entry in (self.m_qty,self.m_instructions):entry.delete(0,"end")
        self.add_medicine_button.configure(text="Add to prescription")
        self.cancel_medicine_button.grid_remove()

    def _add_item(self) -> None:
        name=self.m_name.get().strip()
        if not name:
            self._focus_field(self.m_name)
            messagebox.showwarning("Medicine name needed","Enter the medicine name before adding it.");return
        # item=dict(name=name,dosage=self.m_dosage.get().strip(),quantity=self.m_qty.get().strip(),instructions=self.m_instructions.get().strip())
        item=dict(name=name,dosage="",quantity=self.m_qty.get().strip(),instructions=self.m_instructions.get().strip())
        if self._editing_item is None:self.items.append(item)
        else:self.items[self._editing_item]=item
        self._cancel_item_edit();self._refresh_items()
        self.workflow_status.set(f"{len(self.items)} medicine(s) added. Add another medicine or click Review & save.")
        self.m_name.focus_set()

    def _edit_item(self) -> None:
        selection=self.items_tree.selection()
        if not selection:
            self.workflow_status.set("Select a medicine from the list first.");return
        if self.m_name.get().strip() and not messagebox.askyesno("Replace medicine entry?","Discard the medicine changes currently in the entry fields?"):return
        self._editing_item=self.items_tree.index(selection[0])
        item=self.items[self._editing_item]
        self.m_name.set(item["name"])
        # for entry,key in [(self.m_dosage,"dosage"),(self.m_qty,"quantity"),(self.m_instructions,"instructions")]:
        for entry,key in [(self.m_qty,"quantity"),(self.m_instructions,"instructions")]:
            entry.delete(0,"end");entry.insert(0,item[key])
        self.add_medicine_button.configure(text="Save medicine changes")
        self.cancel_medicine_button.grid()
        self.workflow_status.set("Editing a medicine. Save medicine changes or Cancel changes to keep the original.")
        self._focus_field(self.m_name)

    def _remove_item(self) -> None:
        selection=self.items_tree.selection()
        if not selection:
            self.workflow_status.set("Select a medicine from the list first.");return
        if self._editing_item is not None:
            self.workflow_status.set("Save or cancel the medicine changes before removing a row.");return
        self._removed_items=[(self.items_tree.index(row),dict(self.items[self.items_tree.index(row)])) for row in selection]
        for index,item in sorted(self._removed_items,reverse=True):del self.items[index]
        self.undo_medicine_button.state(["!disabled"])
        self._refresh_items();self.workflow_status.set("Medicine removed. Click Undo removal if this was a mistake.")

    def _undo_remove(self):
        if self._editing_item is not None:
            self.workflow_status.set("Save or cancel medicine changes before undoing a removal.");return
        for index,item in sorted(self._removed_items):self.items.insert(index,item)
        self._removed_items=[];self.undo_medicine_button.state(["disabled"])
        self._refresh_items();self.workflow_status.set("Removed medicine(s) restored.")

    def _focus_field(self,widget):
        self.notebook.select(self.new_rx_tab);self.update_idletasks()
        canvas=self._page_canvases[str(self.new_rx_tab)]
        region=canvas.bbox("all")
        if region:
            y=widget.winfo_rooty()-canvas.winfo_rooty()+canvas.canvasy(0)-90
            canvas.yview_moveto(max(0,y)/max(1,region[3]))
        widget.focus_set()

    def _has_draft(self):
        # return bool(self.items or any(w.get().strip() for w in (self.p_first,self.p_middle,self.p_last,self.p_age,self.p_address,self.p_sex,self.p_civil,self.ph_name,self.ph_license,self.ph_ptr,self.m_name,self.m_dosage,self.m_qty,self.m_instructions,self.notes_entry)) or self.ph_signature.get())
        return bool(self.items or any(w.get().strip() for w in (self.p_first,self.p_middle,self.p_last,self.p_age,self.p_address,self.p_sex,self.p_civil,self.ph_name,self.ph_license,self.ph_ptr,self.m_name,self.m_qty,self.m_instructions,self.notes_entry)) or self.ph_signature.get())

    def _confirm_exit(self):
        if (self._has_draft() or self.opd_editor.has_draft() or self.opd_layout_editor.dirty or self.template_editor.dirty) and not messagebox.askyesno("Close without saving?","There are unsaved form or layout changes. Close the app and discard them?"):
            return
        self.destroy()

    def _show_help(self):
        messagebox.showinfo("How to create a prescription",
            "1. PATIENT: Search for a saved patient, or fill in a new patient's details.\n\n"
            "2. DOCTOR: Choose the doctor. Saved details and signature fill in automatically.\n\n"
            "3. MEDICINES: Enter a medicine and its instructions, then click Add to prescription. Repeat for each medicine.\n\n"
            "4. REVIEW: Click Review & save. Check every page, then Save prescription. Back to editing returns to your form.\n\n"
            "SAVED PRESCRIPTIONS: Find, open, or reuse a previous prescription.\n\n"
            "PAGE LAYOUT: Change where pictures and signatures print. Routine entry does not require changing this tab.")

    def _confirm_clear_form(self) -> None:
        if messagebox.askyesno("Clear prescription?", "Clear the current form and its medicine list? Saved records will remain available."):
            self._clear_form()

    def _clear_form(self) -> None:
        self._cancel_item_edit()
        self._removed_items=[]
        self.undo_medicine_button.state(["disabled"])
        self.workflow_status.set("Start by choosing a saved patient or entering a new patient below.")
        self.medicine_status.set("No medicines added yet. Fill in the medicine above, then click Add to prescription.")
        for e in [self.p_first, self.p_middle, self.p_last,
                  # self.ph_license, self.ph_ptr, self.notes_entry, self.m_dosage, self.m_qty, self.m_instructions]:
                  self.ph_license, self.ph_ptr, self.notes_entry, self.m_qty, self.m_instructions]:
            e.delete(0, "end")
        self.m_name.set("")
        self.p_address.set("")
        self.p_age.delete(0, "end")
        self.ph_signature.set("")
        self.rx_date.set(datetime.date.today())
        self.p_picker.set("")
        self.ph_name.set("")
        self.p_sex.set("")
        self._set_civil_status("")
        self.items = []
        for row in self.items_tree.get_children():
            self.items_tree.delete(row)
        self._refresh_live_preview()

    def _collect_draft(self):
        first,last=self.p_first.get().strip(),self.p_last.get().strip()
        if not first or not last:
            self._focus_field(self.p_first if not first else self.p_last)
            messagebox.showwarning("Patient name needed","Enter the patient's first and last name.");return None
        if not self.ph_name.get().strip():
            self._focus_field(self.ph_name)
            messagebox.showwarning("Doctor needed","Choose or enter the doctor's name.");return None
        if self.m_name.get().strip() or self._editing_item is not None:
            self._focus_field(self.m_name)
            messagebox.showwarning("Finish medicine entry","Click Add to prescription or Save medicine changes first. You can also cancel the changes.");return None
        if not self.items:
            self._focus_field(self.m_name)
            messagebox.showwarning("Add a medicine","Add at least one medicine to this prescription.");return None
        age=self._read_age()
        if age is None:return None
        civil=self._read_civil_status()
        if civil is None:return None
        date=parse_birthday(self.rx_date.get())
        if date is None:
            self._focus_field(self.rx_date)
            messagebox.showwarning("Invalid date","Enter a valid prescription date (MM/DD/YYYY).");return None
        try:
            template=self.template_editor._collect_template()
            if not 6<=template["header_font_size"]<=30 or not 6<=template["body_font_size"]<=22:
                raise ValueError("Check the text sizes in Template Editor.")
        except Exception as exc:
            messagebox.showwarning("Template settings",str(exc));return None
        return dict(patient=dict(first_name=first,middle_name=self.p_middle.get().strip(),last_name=last,age=age,
                    sex=self.p_sex.get(),civil_status=civil,address=self.p_address.get().strip()),
                physician=dict(name=ensure_dr_prefix(self.ph_name.get()),license_no=self.ph_license.get().strip(),
                    ptr_no=self.ph_ptr.get().strip(),signature_path=self.ph_signature.get()),
                items=[dict(item) for item in self.items],notes=self.notes_entry.get().strip(),date=date.isoformat(),template=template)

    def _generate(self) -> None:
        draft=self._collect_draft()
        if draft is not None:self._save_draft(draft)

    def _save_draft(self,draft):
        patient,physician=draft["patient"],draft["physician"]
        set_setting("template",draft["template"])
        patient_id=find_or_create_patient(patient["first_name"],patient["middle_name"],patient["last_name"],patient["age"],patient["sex"],patient["address"],patient["civil_status"])
        physician_id=find_or_create_physician(physician["name"],physician["license_no"],physician["ptr_no"],physician["signature_path"])
        if patient["address"]:add_barangay(patient["address"])
        # for item in draft["items"]:find_or_create_medicine(item["name"],item["dosage"],item["instructions"])
        for item in draft["items"]:find_or_create_medicine(item["name"],None,item["instructions"])
        prescription_id,_=save_prescription(patient_id,physician_id,draft["notes"],draft["items"],date_issued=draft["date"])
        path=generate_pdf(prescription_id)
        self._refresh_caches();self._refresh_history();self._clear_form()
        if messagebox.askyesno("Prescription saved",f"Prescription #{prescription_id} saved for {full_name(patient)}.\n\nOpen the printable copy now?"):open_file(path)
        return True

    def _open_selected_history_pdf(self) -> None:
        sel = self.history_tree.selection()
        if not sel:
            messagebox.showinfo("No selection", "Select a row in the history list first.")
            return
        values = self.history_tree.item(sel[0], "values")
        if values[1] == "OPD":
            try: open_file(export_opd(int(values[0])))
            except Exception as exc: messagebox.showerror("Could not open PDF",str(exc))
            return
        prescription_id = int(values[0])
        presc, *_ = get_prescription_full(prescription_id)
        path = presc["pdf_path"]
        if path and os.path.exists(path):
            open_file(path)
        else:
            path = generate_pdf(prescription_id)
            open_file(path)

    def preview_print(self) -> None:
        """Review current form data before saving."""
        self._open_pdf_editor()
