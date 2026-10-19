"""
Reusable custom widgets:

- DateEntry: a plain entry that auto-inserts slashes as digits are typed
  (09032004 -> 09/03/2004), plus a small popup calendar.
- AutocompleteCombobox: a ttk.Combobox that fuzzy-filters and opens its
  dropdown as the user types.
"""

from __future__ import annotations

import calendar as calmod
import datetime
import tkinter as tk
from tkinter import ttk
from typing import Any

from .database import parse_birthday
from .fuzzy import fuzzy_filter


class DateEntry(ttk.Frame):
    """Plain entry that auto-inserts slashes as you type digits.

    Examples while typing:
        0 -> 0
        09 -> 09/
        0903 -> 09/03/
        09032004 -> 09/03/2004
    Also accepts paste of 09032004 or 09/03/2004.
    Calendar button still available for picking.
    """

    def __init__(self, parent: tk.Misc, default: datetime.date | None = None, width: int = 14, **kwargs: Any) -> None:
        super().__init__(parent, **kwargs)
        self._default = default  # None = start empty; date = prefill
        self._var = tk.StringVar()
        self._formatting = False

        self._entry = ttk.Entry(self, textvariable=self._var, width=width)
        self._entry.pack(side="left", fill="x", expand=True)
        ttk.Button(self, text="\U0001F4C5", width=3, command=self._open_simple_picker).pack(side="left", padx=(2, 0))

        if isinstance(self._default, datetime.date):
            self._var.set(f"{self._default.month:02d}/{self._default.day:02d}/{self._default.year}")

        self._entry.bind("<KeyRelease>", self._on_key)
        self._entry.bind("<FocusOut>", self._on_focus_out)

    def get(self) -> str:
        return self._var.get().strip()

    def set(self, value: datetime.date | str | None) -> None:
        if isinstance(value, datetime.date):
            d = value
        else:
            d = parse_birthday(str(value or ""))
            if not d:
                # try raw 8 digits
                digits = "".join(ch for ch in str(value or "") if ch.isdigit())
                if len(digits) == 8:
                    try:
                        d = datetime.date(int(digits[4:8]), int(digits[0:2]), int(digits[2:4]))
                    except ValueError:
                        d = None
        if d:
            self._formatting = True
            self._var.set(f"{d.month:02d}/{d.day:02d}/{d.year}")
            self._formatting = False
        else:
            self._formatting = True
            self._var.set("")
            self._formatting = False

    def clear(self) -> None:
        self._formatting = True
        self._var.set("")
        self._formatting = False

    def _on_key(self, event: tk.Event) -> None:
        # Format after Tk finishes the edit so the inserted slash does not
        # interrupt the next digit typed by the user.
        #let me be the one, who break it up so you dont have to make excuses, let the oceans rice
        if event.keysym in ("Left", "Right", "Home", "End", "Tab", "Return"):
            return
        self._format_digits()

    def _format_digits(self) -> None:
        """Take whatever is in the box, keep digits, re-insert slashes."""
        raw = self._var.get()
        # caret position roughly by digit count before cursor
        try:
            cursor = self._entry.index("insert")
            digits_before = sum(1 for ch in raw[:cursor] if ch.isdigit())
        except Exception:
            digits_before = 0

        digits = "".join(ch for ch in raw if ch.isdigit())[:8]

        if len(digits) <= 2:
            formatted = digits
        elif len(digits) <= 4:
            formatted = digits[:2] + "/" + digits[2:]
        else:
            formatted = digits[:2] + "/" + digits[2:4] + "/" + digits[4:]

        if formatted == raw:
            return

        self._formatting = True
        self._var.set(formatted)
        self._formatting = False

        # restore cursor after the same number of digits
        new_pos = 0
        seen = 0
        for i, ch in enumerate(formatted):
            if seen >= digits_before:
                new_pos = i
                break
            if ch.isdigit():
                seen += 1
            new_pos = i + 1
        try:
            self._entry.icursor(new_pos)
        except Exception:
            pass

    def _on_focus_out(self, event: tk.Event | None = None) -> None:
        """On leave, try to normalize to a real MM/DD/YYYY if possible."""
        d = parse_birthday(self._var.get())
        if d:
            self.set(d)
        else:
            digits = "".join(ch for ch in self._var.get() if ch.isdigit())
            if len(digits) == 8:
                try:
                    d = datetime.date(int(digits[4:8]), int(digits[0:2]), int(digits[2:4]))
                    self.set(d)
                except ValueError:
                    pass

    def _open_simple_picker(self) -> None:
        top = tk.Toplevel(self)
        top.title("Select date")
        top.resizable(False, False)
        top.transient(self.winfo_toplevel())
        top.grab_set()

        today = parse_birthday(self._var.get()) or (
            self._default if isinstance(self._default, datetime.date) else datetime.date.today()
        )
        year_var = tk.IntVar(value=today.year)
        month_var = tk.IntVar(value=today.month)

        header = ttk.Frame(top)
        header.pack(padx=8, pady=6)
        month_lbl = ttk.Label(header, width=16, anchor="center")
        ttk.Button(header, text="<", width=3,
                   command=lambda: self._shift(month_var, year_var, -1, cal_frame, month_lbl)).pack(side="left")
        month_lbl.pack(side="left", padx=4)
        ttk.Button(header, text=">", width=3,
                   command=lambda: self._shift(month_var, year_var, 1, cal_frame, month_lbl)).pack(side="left")

        cal_frame = ttk.Frame(top)
        cal_frame.pack(padx=8, pady=4)
        self._build_cal(cal_frame, month_var.get(), year_var.get(), month_lbl, top)

        ttk.Button(top, text="Today",
                   command=lambda: (self.set(datetime.date.today()), top.destroy())).pack(pady=6)

    def _shift(self, month_var: tk.IntVar, year_var: tk.IntVar, delta: int, cal_frame: ttk.Frame, month_lbl: ttk.Label) -> None:
        m = month_var.get() + delta
        y = year_var.get()
        if m < 1:
            m, y = 12, y - 1
        elif m > 12:
            m, y = 1, y + 1
        month_var.set(m)
        year_var.set(y)
        self._build_cal(cal_frame, m, y, month_lbl, cal_frame.winfo_toplevel())

    def _build_cal(self, cal_frame: ttk.Frame, month: int, year: int, month_lbl: ttk.Label, top: tk.Misc) -> None:
        for w in cal_frame.winfo_children():
            w.destroy()
        month_lbl.config(text=f"{calmod.month_name[month]} {year}")
        for i, day in enumerate(["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"]):
            ttk.Label(cal_frame, text=day, width=3, anchor="center").grid(row=0, column=i)
        t = datetime.date.today()
        for r, week in enumerate(calmod.Calendar(firstweekday=0).monthdayscalendar(year, month), start=1):
            for c, day in enumerate(week):
                if day == 0:
                    ttk.Label(cal_frame, text="", width=3).grid(row=r, column=c)
                else:
                    def make_cmd(dd=day, mm=month, yy=year):
                        def cmd():
                            self.set(datetime.date(yy, mm, dd))
                            top.destroy()
                        return cmd
                    btn = ttk.Button(cal_frame, text=str(day), width=3, command=make_cmd())
                    if t.year == year and t.month == month and t.day == day:
                        # Highlight "today". The previous implementation called
                        # btn.state(["Accent.TButton"]) which is invalid (state()
                        # expects state flags like "disabled", not a style name)
                        # and silently did nothing. Applying the style directly
                        # is what actually highlights the button\
                        #  meron din naman palang ganda ang buhay pwede ng mangarap
                        # meron din naman palang gannda ang buhay, pwede ng mangaraap
                        # and now, the end is near, and so I face, the final curtain
                        #holy shit, I actually fucked up my alizon, wtf, for the longest time
                        #I fucked that up becuase I rushed things 
                        try:
                            btn.configure(style="Accent.TButton")
                        except Exception:
                            pass
                    btn.grid(row=r, column=c, padx=1, pady=1)


class AutocompleteCombobox(ttk.Combobox):
    """Editable dropdown with non-modal, keyboard-accessible suggestions."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.auto_dropdown = bool(kwargs.pop("auto_dropdown", False))
        self._text = tk.StringVar()
        kwargs["textvariable"] = self._text
        super().__init__(*args, **kwargs)
        self._all_values = []
        self._suggestion_window = None
        self._listbox = None
        self._dropdown_job = None
        self._setting = False
        self._text.trace_add("write", self._text_changed)
        self.bind("<Down>", lambda e: self._navigate(1))
        self.bind("<Up>", lambda e: self._navigate(-1))
        self.bind("<Return>", self._on_search)
        self.bind("<Escape>", self._dismiss)
        self.bind("<Tab>", self._hide_suggestions)
        self.bind("<FocusOut>", lambda e: self.after_idle(self._check_focus))
        self.bind("<Button-1>", self._click_arrow)
        self.bind("<Destroy>", self._cleanup)
        self._owner = self.winfo_toplevel()
        self._owner_bindings = [(sequence, self._owner.bind(sequence, handler, add="+"))
            for sequence, handler in (("<ButtonPress-1>", self._outside_click),
                                      ("<Configure>", self._moved),
                                      ("<MouseWheel>", self._hide_suggestions),
                                      ("<Unmap>", self._hide_suggestions))]

    def set_completion_list(self, values: list[str]) -> None:
        self._all_values = list(values)
        self["values"] = self._all_values
        self._hide_suggestions()

    def set(self, value: str) -> None:
        self._setting = True
        try:
            super().set(value)
        finally:
            self._setting = False
        self._hide_suggestions()

    def _text_changed(self, *_args) -> None:
        self._hide_suggestions()
        self["values"] = fuzzy_filter(self.get(), self._all_values)
        if not self._setting and self.auto_dropdown and self.get().strip() and self["values"]:
            self._dropdown_job = self.after_idle(self._show_dropdown)

    def _check_focus(self) -> None:
        if self.winfo_exists() and self.focus_get() is not self:
            self._hide_suggestions()

    def _outside_click(self, event) -> None:
        if event.widget is not self:
            self._hide_suggestions()

    def _moved(self, event) -> None:
        ancestor = self
        while ancestor is not None:
            if event.widget is ancestor:
                self._hide_suggestions()
                break
            ancestor = ancestor.master

    def _click_arrow(self, event) -> str | None:
        if "arrow" in self.identify(event.x, event.y):
            if self._suggestion_window:
                self._hide_suggestions()
            else:
                self.focus_set()
                self["values"] = fuzzy_filter(self.get(), self._all_values)
                self._show_dropdown()
            return "break"
        return None

    def _dismiss(self, event=None) -> str:
        self._hide_suggestions()
        return "break"

    def _navigate(self, step: int) -> str:
        if not self._suggestion_window:
            self["values"] = fuzzy_filter(self.get(), self._all_values)
            self._show_dropdown()
        box = self._listbox
        if box is not None and box.size():
            selected = box.curselection()
            index = max(0, min(box.size() - 1, selected[0] + step)) if selected else (0 if step > 0 else box.size() - 1)
            box.selection_clear(0, "end")
            box.selection_set(index)
            box.activate(index)
            box.see(index)
        return "break"

    def _on_search(self, event=None) -> str:
        if self._listbox is not None and self._listbox.curselection():
            self._choose_suggestion(self._listbox.curselection()[0])
        elif self._suggestion_window:
            self._hide_suggestions()
        elif not self.auto_dropdown:
            self["values"] = fuzzy_filter(self.get(), self._all_values)
            self._show_dropdown()
        return "break"

    def _show_dropdown(self) -> None:
        self._dropdown_job = None
        self._hide_suggestions()
        if not self.winfo_ismapped() or self.focus_get() is not self or not self["values"]:
            return
        window = tk.Toplevel(self)
        self._suggestion_window = window
        window.withdraw()
        window.overrideredirect(True)
        window.transient(self._owner)
        height = min(len(self["values"]), 8) * 26 + 4
        width = max(self.winfo_width(), 260)
        x = min(self.winfo_rootx(), self.winfo_screenwidth() - width)
        y = self.winfo_rooty() + self.winfo_height()
        if y + height > self.winfo_screenheight():
            y = max(0, self.winfo_rooty() - height)
        window.geometry(f"{width}x{height}+{max(0,x)}+{y}")
        box = tk.Listbox(window, exportselection=False, takefocus=False,
                         font=("Segoe UI", 10), bg="white", fg="#0f172a",
                         selectbackground="#dbeafe", selectforeground="#0f172a",
                         activestyle="none", relief="solid", borderwidth=1,
                         highlightthickness=0)
        scrollbar = ttk.Scrollbar(window, orient="vertical", command=box.yview)
        scrollbar.pack(side="right", fill="y")
        box.pack(side="left", fill="both", expand=True)
        box.configure(yscrollcommand=scrollbar.set)
        for value in self["values"]:
            box.insert("end", value)
        self._listbox = box
        box.bind("<MouseWheel>", self._scroll_suggestions)
        box.bind("<ButtonPress-1>", lambda e: self._choose_suggestion(box.nearest(e.y)))
        window.deiconify()
        window.lift()

    def _scroll_suggestions(self, event) -> str:
        if self._listbox is not None:
            self._listbox.yview_scroll(-int(event.delta / 120), "units")
        return "break"

    def _choose_suggestion(self, index: int) -> str:
        value = self._listbox.get(index)
        self.set(value)
        self.icursor("end")
        self.focus_set()
        self.event_generate("<<ComboboxSelected>>")
        return "break"

    def _hide_suggestions(self, event=None) -> None:
        if self._dropdown_job:
            self.after_cancel(self._dropdown_job)
            self._dropdown_job = None
        if self._suggestion_window is not None:
            self._suggestion_window.destroy()
            self._suggestion_window = None
        self._listbox = None

    def _cleanup(self, event) -> None:
        if event.widget is self:
            self._hide_suggestions()
            for sequence, binding in self._owner_bindings:
                self._owner.unbind(sequence, binding)
#somebody told me you were leaving, I didnt know
#somedody told me you're unhappy, but it doesnt show
#when it rains it pours, but you didnt even notice. it aint rainign 