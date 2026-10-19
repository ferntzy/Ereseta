"""

Renders a prescription as a PDF that matches the official LBHI

prescription form layout, using the currently saved hospital info and

template settings.

"""



from __future__ import annotations



import datetime
import io
from functools import lru_cache

import os

import platform

import subprocess



from reportlab.lib import colors

from reportlab.lib.pdfencrypt import StandardEncryption

from reportlab.lib.units import inch

from reportlab.lib.utils import ImageReader, simpleSplit

from reportlab.pdfgen import canvas



from .formatting import format_quantity
from . import config

from .database import (

    calc_age,

    ensure_dr_prefix,

    full_name,

    get_prescription_full,

    get_setting,

    set_prescription_pdf_path,

)





def _resolve_asset_path(cfg_path: str | None, fallback_filename: str | None) -> str | None:

    """Return a usable asset path from the saved template or bundled project assets."""

    candidates = []

    if cfg_path:

        candidates.append(cfg_path)

    if fallback_filename:

        candidates.append(os.path.join(config.ASSETS_DIR, fallback_filename))

    for candidate in candidates:

        if candidate and os.path.exists(candidate):

            return candidate

    return None





@lru_cache(maxsize=32)
def _cached_asset(path, modified, remove_white):
    from PIL import Image, ImageChops, ImageOps, ImageDraw
    with Image.open(path) as source:
        image = source.convert("RGBA")
    if remove_white:
        # Remove only near-white regions connected to the outside edge.
        # Enclosed white lettering/details and existing alpha remain intact.
        r,g,b,alpha = image.split()
        light = ImageChops.darker(ImageChops.darker(r,g),b).point(lambda v: 255 if v >= 240 else 0)
        padded = ImageOps.expand(light, border=1, fill=255)
        ImageDraw.floodfill(padded, (0,0), 128)
        keep = padded.crop((1,1,image.width+1,image.height+1)).point(lambda v: 0 if v == 128 else 255)
        image.putalpha(ImageChops.multiply(alpha,keep))
    return ImageReader(image)


def _asset_reader(path, remove_white=True):
    return _cached_asset(os.path.abspath(path), os.stat(path).st_mtime_ns, remove_white)


def _secure_canvas(path: str, pagesize):

    """Create a canvas with editing restrictions so generated PDFs are not freely editable."""

    return canvas.Canvas(

        path,

        pagesize=pagesize,

        encrypt=StandardEncryption(

            userPassword="",

            ownerPassword="EResetaOwner",

            canPrint=1,

            canModify=0,

            canCopy=0,

            canAnnotate=0,

            strength=128,

        ),

    )





def generate_pdf(prescription_id: int) -> str:

    """Generate PDF that closely matches the official LBHI prescription form layout."""

    presc, patient, physician, items = get_prescription_full(prescription_id)

    hospital = get_setting("hospital", config.DEFAULT_HOSPITAL)

    tmpl = get_setting("template", config.DEFAULT_TEMPLATE)



    fname = f"Rx_{prescription_id:05d}_{full_name(patient).replace(' ', '_')}.pdf"
    path = os.path.join(config.OUTPUT_DIR, fname)
    _render_prescription(path, presc, patient, physician, items, hospital, tmpl)
    set_prescription_pdf_path(prescription_id, path)
    return path


def _render_prescription(path, presc, patient, physician, items, hospital, tmpl):
    page_w = float(tmpl.get("page_width_in", 5.5)) * inch
    page_h = float(tmpl.get("page_height_in", 8.5)) * inch
    page_size = (page_w, page_h)
    margin = float(tmpl.get("margin_in", .40)) * inch
    accent = colors.HexColor(tmpl.get("accent_color", "#0f172a"))

    c = _secure_canvas(path, page_size)

    w, h = page_size

    y = h - margin



    # ---------- LOGO (drawn behind text - never moves the letterhead) ----------

    logo_cfg = tmpl.get("logo", {})

    logo_path = _resolve_asset_path(logo_cfg.get("path"), "logo.png")

    if logo_cfg.get("enabled", bool(logo_path)) and logo_path:

        try:

            lw = float(logo_cfg.get("w_pct", 0.16)) * w

            lh = float(logo_cfg.get("h_pct", 0.09)) * h

            lx = float(logo_cfg.get("x_pct", 0.42)) * w

            # Template Editor Y is measured from the TOP.
            ly = h - (float(logo_cfg.get("y_pct", 0.04)) * h) - lh

            lx = max(0, min(lx, w - lw))

            ly = max(0, min(ly, h - lh))

            c.drawImage(_asset_reader(logo_path, tmpl.get("transparent_images", True)), lx, ly, width=lw, height=lh,

                        preserveAspectRatio=True, mask="auto")

        except Exception:

            pass



    # ---------- LETTERHEAD (fixed position - independent of logo) ----------

    # The hospital name and the separator line use the template's accent

    # color so that "Accent color" in the Template Editor actually has a

    # visible effect on the printed prescription.

    header_size = int(tmpl.get("header_font_size", 11))

    c.setFillColor(accent)

    c.setFont("Helvetica-Bold", header_size)

    c.drawCentredString(w / 2, y, hospital.get("name", "").upper())

    y -= 11

    c.setFillColor(colors.black)

    c.setFont("Helvetica", 7)

    c.drawCentredString(w / 2, y, hospital.get("address", ""))

    y -= 9

    c.drawCentredString(w / 2, y, f"Email add: {hospital.get('email', '')}")

    y -= 9

    c.drawCentredString(w / 2, y, f"Tele: {hospital.get('tel', '')}")

    y -= 9

    c.drawCentredString(w / 2, y, f"Mobile Nos: {hospital.get('mobile', '')}")

    y -= 9

    if tmpl.get("show_motto", True) and hospital.get("motto"):

        c.setFont("Helvetica-Oblique", 6.5)

        c.drawCentredString(w / 2, y, hospital["motto"])

        y -= 8



    # thin separator line, tinted with the accent color

    c.setStrokeColor(accent)

    c.setLineWidth(0.8)

    c.line(margin, y, w - margin, y)

    c.setStrokeColor(colors.black)

    y -= 14



    # ---------- PATIENT BLOCK (form style like the sample) ----------

    body = int(tmpl.get("body_font_size", 9))

    age = patient["age"] if "age" in patient.keys() else calc_age(patient["birthday"])

    age_str = str(age) if age is not None else ""

    # format date as M/D/YYYY (or MM/DD/YYYY)

    try:

        d = datetime.date.fromisoformat(presc["date_issued"])

        date_str = f"{d.month}/{d.day}/{d.year}"

    except Exception:

        date_str = presc["date_issued"]



    def fit_text(text, font_name, max_size, min_size, max_width):

        """Shrink font until the text fits on one line (or hit min_size)."""

        size = max_size

        while size > min_size:

            if c.stringWidth(text, font_name, size) <= max_width:

                return size

            size -= 0.5

        return min_size



    def draw_underlined_value(text, x, y_pos, max_w, font_name="Helvetica", max_size=None, min_size=6):

        max_size = max_size or body

        size = fit_text(text, font_name, max_size, min_size, max_w)

        c.setFont(font_name, size)

        c.drawString(x, y_pos, text)

        c.setStrokeColor(colors.Color(0.3, 0.3, 0.3))

        c.setLineWidth(0.4)

        c.line(x, y_pos - 2, x + max_w, y_pos - 2)

        return size



    label_w = 0.95 * inch



    # NAME (full width) - auto-shrink if long

    c.setFont("Helvetica-Bold", body - 0.5)

    c.drawString(margin, y, "NAME:")

    name_val = full_name(patient).upper()

    name_max_w = w - margin - (margin + label_w)

    draw_underlined_value(name_val, margin + label_w, y, name_max_w, "Helvetica", body, 6.5)

    y -= 13



    # AGE  SEX          CIVIL STATUS

    c.setFont("Helvetica-Bold", body - 0.5)

    c.drawString(margin, y, "AGE:")

    c.setFont("Helvetica", body)

    c.drawString(margin + 0.45 * inch, y, age_str)

    c.line(margin + 0.45 * inch, y - 2, margin + 0.85 * inch, y - 2)



    c.setFont("Helvetica-Bold", body - 0.5)

    c.drawString(margin + 1.0 * inch, y, "SEX:")

    sex_val = (patient["sex"] or "").upper()

    draw_underlined_value(sex_val, margin + 1.4 * inch, y, 0.85 * inch, "Helvetica", body, 6.5)



    c.setFont("Helvetica-Bold", body - 0.5)

    c.drawString(margin + 2.5 * inch, y, "CIVIL STATUS:")

    civil_val = (patient["civil_status"] or "").upper()

    civil_x = margin + 3.55 * inch

    civil_max = w - margin - civil_x

    draw_underlined_value(civil_val, civil_x, y, max(civil_max, 0.6 * inch), "Helvetica", body, 6.5)

    y -= 13



    # ADDRESS                    DATE - keep both on one line; shrink address if needed

    c.setFont("Helvetica-Bold", body - 0.5)

    c.drawString(margin, y, "ADDRESS:")

    addr = (patient["address"] or "").upper()

    date_block_w = 1.35 * inch

    addr_x = margin + label_w

    addr_max_w = w - margin - date_block_w - addr_x

    draw_underlined_value(addr, addr_x, y, max(addr_max_w, 1.2 * inch), "Helvetica", body, 6)



    c.setFont("Helvetica-Bold", body - 0.5)

    c.drawString(w - margin - date_block_w, y, "DATE:")

    date_x = w - margin - 0.95 * inch

    draw_underlined_value(date_str, date_x, y, 0.95 * inch, "Helvetica", body, 6.5)

    y -= 16



    # ---------- Rx SYMBOL ----------

    rx_cfg = tmpl.get("rx_symbol", {})

    if rx_cfg.get("enabled", tmpl.get("show_rx_symbol", True)):

        rx_path = _resolve_asset_path(
            rx_cfg.get("path", tmpl.get("rx_symbol_path")),
            "Rx.png",
        )

        rx_w = float(rx_cfg.get("w_pct", 0.10)) * w

        rx_h = float(rx_cfg.get("h_pct", 0.08)) * h

        rx_x = float(rx_cfg.get("x_pct", margin / w)) * w

        # Template Editor Y is measured from the TOP.
        rx_y = h - (float(rx_cfg.get("y_pct", 0.30)) * h) - rx_h

        rx_x = max(0, min(rx_x, w - rx_w))

        rx_y = max(0, min(rx_y, h - rx_h))

        if rx_path and os.path.exists(rx_path):

            c.drawImage(
                _asset_reader(rx_path, tmpl.get("transparent_images", True)),
                rx_x,
                rx_y,
                width=rx_w,
                height=rx_h,
                preserveAspectRatio=False,
                mask="auto",
            )

        else:

            c.setFont(
                "Helvetica-Bold",
                max(10, min(int(rx_h * 0.65), 72)),
            )

            c.setFillColor(colors.black)

            c.drawString(
                rx_x,
                rx_y + (rx_h * 0.15),
                "Rx",
            )

    # Keep the medicine block in the same position when the symbol is hidden.

    y -= 16



    # ---------- MEDICINE LIST (sample style: name left, #qty right, Sig below) ----------

    y -= 10

    med_left = margin + 0.15 * inch

    qty_right = w - margin
    qty_left = qty_right - 0.7 * inch  # Reserved quantity area, including handwriting.



    for item in items:

        name_part = item["medicine_name"] or ""

        # Dosage rendering temporarily disabled; original implementation retained.
        # dosage_part = item["dosage"] or ""

        # # avoid repeating dosage if already in the name

        # if dosage_part and dosage_part.lower() in name_part.lower():

        #     line = name_part

        # else:

        #     line = f"{name_part} {dosage_part}".strip()



        line = name_part

        c.setFont("Helvetica-Bold", body)

        # draw medicine name

        name_width = qty_left - med_left - 8

        wrapped = simpleSplit(line.upper(), "Helvetica-Bold", body, name_width)

        for i, wl in enumerate(wrapped):

            c.drawString(med_left, y, wl)

            if i == 0:

                # Align every quantity marker at the start of the quantity column.

                qty_txt = format_quantity(item["quantity"])

                c.setFont("Helvetica-Bold", body)

                # The same origin keeps blank and filled markers vertically aligned.
                c.drawString(qty_left, y, qty_txt)

            y -= 11



        if item["instructions"]:

            c.setFont("Helvetica-Oblique", body - 1)

            sig_prefix = "Sig: "

            sig_lines = simpleSplit(sig_prefix + item["instructions"].upper(), "Helvetica-Oblique", body - 1,

                                    w - 2 * margin - 0.3 * inch)

            for sl in sig_lines:

                c.drawString(med_left + 0.1 * inch, y, sl)

                y -= 10

        y -= 7  # gap between medicines



        if y < 1.5 * inch:

            c.showPage()

            y = h - margin

            c.setFont("Helvetica", body)



    if presc["notes"]:
        note_width = max(36, w - 2 * margin - 2.45 * inch)
        note_lines = simpleSplit(f"Notes: {presc['notes']}", "Helvetica-Oblique", 7.5, note_width)
        capacity = max(1, int((min(y - 18, 1.45 * inch) - 0.55 * inch) / 9))
        while len(note_lines) > capacity:
            c.setFont("Helvetica-Oblique", 7.5)
            for i, line in enumerate(note_lines[:capacity]):
                c.drawString(margin, 0.55 * inch + (capacity - 1 - i) * 9, line)
            note_lines = note_lines[capacity:]
            c.showPage()
            capacity = max(1, int((h - margin - 0.55 * inch) / 9))
        c.setFont("Helvetica-Oblique", 7.5)
        for i, line in enumerate(note_lines):
            c.drawString(margin, 0.55 * inch + (len(note_lines) - 1 - i) * 9, line)

    # ---------- SIGNATURE BLOCK (bottom-right, matches sample) ----------

    sig_cfg = dict(tmpl.get("signature_img", {}))
    sig_cfg["path"] = physician["signature_path"] or ""
    sig_cfg["enabled"] = sig_cfg.get("show_assigned", True) and bool(sig_cfg["path"])

    # keep signature area near the bottom

    sig_block_bottom = 0.55 * inch

    sig_center_x = w - margin - 1.15 * inch



    # signature image (handwritten)

    if sig_cfg.get("enabled") and sig_cfg.get("path") and os.path.exists(sig_cfg["path"]):

        try:

            sw = float(sig_cfg.get("w_pct", 0.28)) * w

            sh = float(sig_cfg.get("h_pct", 0.07)) * h

            sx = float(sig_cfg.get("x_pct", 0.58)) * w

            sy = float(sig_cfg.get("y_pct", 0.16)) * h

            c.drawImage(_asset_reader(sig_cfg["path"], tmpl.get("transparent_images", True)), sx, sy, width=sw, height=sh,

                        preserveAspectRatio=True, mask="auto")

        except Exception:

            pass



    ph_name = ensure_dr_prefix(physician["name"] or "")

    name_max_w = 2.3 * inch

    ph_size = fit_text(ph_name, "Helvetica", 8, 6, name_max_w)

    c.setFont("Helvetica", ph_size)

    c.drawCentredString(sig_center_x, sig_block_bottom + 28, ph_name)

    c.setFont("Helvetica", 7)

    c.drawCentredString(sig_center_x, sig_block_bottom + 16, f"Lic #: {physician['license_no'] or ''}")

    c.drawCentredString(sig_center_x, sig_block_bottom + 6, f"PTR: {physician['ptr_no'] or ''}")



    c.save()

def prescription_pdf_bytes(patient, physician, items, *, notes="", date_issued=None, template=None):
    """Render an unsaved draft without changing database records or files."""
    tmpl = template if template is not None else get_setting("template", config.DEFAULT_TEMPLATE)
    hospital = get_setting("hospital", config.DEFAULT_HOSPITAL)
    presc = dict(notes=notes, date_issued=date_issued or datetime.date.today().isoformat())
    rows = [dict(medicine_name=item["name"], dosage=item.get("dosage", ""),
                 quantity=item.get("quantity", ""), instructions=item.get("instructions", "")) for item in items]
    output = io.BytesIO()
    _render_prescription(output, presc, patient, physician, rows, hospital, tmpl)
    return output.getvalue()


def template_pdf_bytes(template=None, signature_path=None):
    """Use the production renderer with sample patient/medicine data."""
    tmpl = template if template is not None else get_setting("template", config.DEFAULT_TEMPLATE)
    hospital = get_setting("hospital", config.DEFAULT_HOSPITAL)
    patient = dict(first_name="SAMPLE", middle_name="", last_name="PATIENT", age=35,
                   sex="Female", civil_status="Single", address="SAMPLE ADDRESS")
    physician = dict(name="Sample physician", license_no="--", ptr_no="--", signature_path=signature_path or "")
    presc = dict(date_issued=datetime.date.today().isoformat(), notes="Sample follow-up note")
    items = [dict(medicine_name=m.get("name",""), dosage=m.get("dosage",""),
                  quantity=m.get("quantity",""), instructions=m.get("instructions",""))
             for m in tmpl.get("preview_medicines",[]) if m.get("name")]
    output = io.BytesIO()
    _render_prescription(output, presc, patient, physician, items, hospital, tmpl)
    return output.getvalue()


def generate_template_preview(signature_path=None, template=None):
    path = os.path.join(config.OUTPUT_DIR, "Template_Preview.pdf")
    with open(path,"wb") as output:
        output.write(template_pdf_bytes(template, signature_path))
    return path


def open_file(path: str) -> None:

    """Open a file with the OS's default application (best-effort)."""

    try:

        if platform.system() == "Windows":

            os.startfile(path)  # noqa

        elif platform.system() == "Darwin":

            subprocess.run(["open", path])

        else:

            subprocess.run(["xdg-open", path])

    except Exception:

        pass
