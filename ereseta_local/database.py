"""
SQLite persistence layer: schema setup, settings storage, and CRUD /
lookup helpers for patients, physicians, medicines, barangays, and
prescriptions. Also holds the small date-handling helpers shared across
the app (parsing, age calculation, normalization).

Nothing in this module imports tkinter or reportlab, so it can be
exercised and unit-tested headlessly.
"""

from __future__ import annotations

import csv
import datetime
import json
import os
import sqlite3
from typing import Any

from . import config


# --------------------------------------------------------------------------
# Connection / schema
# --------------------------------------------------------------------------

def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(config.DB_FILE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    conn = get_conn()
    cur = conn.cursor()
    cur.executescript(
        """
        CREATE TABLE IF NOT EXISTS patients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            first_name TEXT NOT NULL,
            middle_name TEXT,
            last_name TEXT NOT NULL,
            birthday TEXT,
            sex TEXT,
            address TEXT,
            civil_status TEXT,
            UNIQUE(first_name, middle_name, last_name)
        );

        CREATE TABLE IF NOT EXISTS physicians (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            license_no TEXT,
            ptr_no TEXT
        );

        CREATE TABLE IF NOT EXISTS medicines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            default_dosage TEXT,
            default_instructions TEXT
        );

        CREATE TABLE IF NOT EXISTS prescriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER NOT NULL,
            physician_id INTEGER NOT NULL,
            date_issued TEXT NOT NULL,
            notes TEXT,
            pdf_path TEXT,
            FOREIGN KEY(patient_id) REFERENCES patients(id),
            FOREIGN KEY(physician_id) REFERENCES physicians(id)
        );

        CREATE TABLE IF NOT EXISTS prescription_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            prescription_id INTEGER NOT NULL,
            medicine_name TEXT NOT NULL,
            dosage TEXT,
            quantity TEXT,
            instructions TEXT,
            FOREIGN KEY(prescription_id) REFERENCES prescriptions(id)
        );

        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        );

        CREATE TABLE IF NOT EXISTS barangays (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE
        );
        """
    )

    from .opd_database import init_opd_schema
    init_opd_schema()

    # Migrate old 'age' column -> birthday if needed
    cols = [r[1] for r in cur.execute("PRAGMA table_info(patients)").fetchall()]
    if "age" in cols and "birthday" not in cols:
        cur.execute("ALTER TABLE patients ADD COLUMN birthday TEXT")
        conn.commit()

    if "age" not in cols:
        cur.execute("ALTER TABLE patients ADD COLUMN age INTEGER")
    for patient in cur.execute("SELECT id, birthday FROM patients WHERE age IS NULL").fetchall():
        cur.execute("UPDATE patients SET age=? WHERE id=?", (calc_age(patient["birthday"]), patient["id"]))
    if "signature_path" not in [r[1] for r in cur.execute("PRAGMA table_info(physicians)")]:
        cur.execute("ALTER TABLE physicians ADD COLUMN signature_path TEXT")

    # Seed hospital + template if missing
    for key, default in [("hospital", config.DEFAULT_HOSPITAL), ("template", config.DEFAULT_TEMPLATE)]:
        row = cur.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        if not row:
            cur.execute("INSERT INTO settings (key, value) VALUES (?,?)", (key, json.dumps(default)))

    # Seed barangays (Leyte + Southern Leyte) once
    count = cur.execute("SELECT COUNT(*) FROM barangays").fetchone()[0]
    if count == 0:
        cur.executemany(
            "INSERT OR IGNORE INTO barangays (name) VALUES (?)",
            [(b,) for b in config.SEED_BARANGAYS],
        )
    conn.commit()
    conn.close()


# --------------------------------------------------------------------------
# Settings
# --------------------------------------------------------------------------

def get_setting(key: str, default: Any = None) -> Any:
    conn = get_conn()
    row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    conn.close()
    if not row:
        return default
    try:
        return json.loads(row["value"])
    except Exception:
        return default


def set_setting(key: str, value: Any) -> None:
    conn = get_conn()
    conn.execute(
        "INSERT OR REPLACE INTO settings (key, value) VALUES (?,?)",
        (key, json.dumps(value)),
    )
    conn.commit()
    conn.close()


# --------------------------------------------------------------------------
# Date helpers
# --------------------------------------------------------------------------

def full_name(row: sqlite3.Row | dict[str, Any]) -> str:
    parts = [row["first_name"], row["middle_name"], row["last_name"]]
    return " ".join(p for p in parts if p)


def parse_birthday(date_str: str | None) -> datetime.date | None:
    """Parse common date formats -> datetime.date or None.

    Accepts: 09/03/2004, 9/3/2004, 2004-09-03, and bare digits 09032004.
    Despite the name, this is used generically for any MM/DD/YYYY-style
    date in the app (birthdays and prescription dates alike).
    """
    if not date_str:
        return None
    s = date_str.strip()
    for fmt in ("%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d", "%m-%d-%Y"):
        try:
            return datetime.datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    # bare 8 digits MMDDYYYY
    digits = "".join(ch for ch in s if ch.isdigit())
    if len(digits) == 8:
        try:
            return datetime.date(int(digits[4:8]), int(digits[0:2]), int(digits[2:4]))
        except ValueError:
            pass
    return None


def calc_age(birthday_str: str | None) -> int | None:
    """Return integer age or None if birthday cannot be parsed."""
    bday = parse_birthday(birthday_str)
    if not bday:
        return None
    today = datetime.date.today()
    age = today.year - bday.year - ((today.month, today.day) < (bday.month, bday.day))
    return max(0, age)


def normalize_birthday(birthday_str: str | None) -> str:
    """Store birthdays as MM/DD/YYYY when possible."""
    bday = parse_birthday(birthday_str)
    if bday:
        return f"{bday.month:02d}/{bday.day:02d}/{bday.year}"
    return (birthday_str or "").strip()


def ensure_dr_prefix(name: str | None) -> str:
    """Always put 'Dr.' in front of physician name (unless already present)."""
    name = (name or "").strip()
    if not name:
        return name
    low = name.lower()
    if low.startswith("dr.") or low.startswith("dr "):
        # normalize to "Dr. Name"
        rest = name[3:].lstrip(" .")
        return f"Dr. {rest}" if rest else "Dr."
    return f"Dr. {name}"


# --------------------------------------------------------------------------
# Tabular file import helper (shared by medicine + barangay bulk import)
# --------------------------------------------------------------------------

def _rows_from_tabular_file(file_path: str) -> list[dict[str, Any]]:
    """Read a CSV or Excel file into a list of {lowercased_header: value} dicts.

    Centralizes the CSV/Excel parsing that medicine and barangay bulk-import
    used to duplicate independently (previously the two code paths could
    silently drift apart).
    """
    ext = os.path.splitext(file_path)[1].lower()
    rows = []

    if ext in (".xlsx", ".xls"):
        try:
            import openpyxl
        except ImportError:
            raise RuntimeError(
                "Reading Excel files requires the 'openpyxl' package.\n"
                "Install it with:  py -m pip install openpyxl\n"
                "Or export/save your file as .csv instead."
            )
        wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
        ws = wb.active
        raw_rows = list(ws.iter_rows(values_only=True))
        if not raw_rows:
            return []
        header = [str(h).strip().lower() if h else "" for h in raw_rows[0]]
        for r in raw_rows[1:]:
            rows.append({header[i]: (r[i] if i < len(r) else None) for i in range(len(header))})
    else:
        with open(file_path, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            reader.fieldnames = [(fn or "").strip().lower() for fn in reader.fieldnames]
            for r in reader:
                rows.append(r)

    # normalize keys once more (defensive, in case a source has mixed case)
    return [{(k or "").strip().lower(): v for k, v in row.items()} for row in rows]


def _pick(row: dict[str, Any], *keys: str) -> str:
    """Return the first non-empty value among the given keys; else, IF NONE
    of those recognized columns exist at all, fall back to the first
    non-empty value in the row (handles single-column, unlabeled files).

    The fallback is intentionally restricted to "none of the keys exist as
    columns" rather than "none of the keys have a value" — the previous
    version fell back whenever the recognized column was merely blank for
    that row, which meant a blank "name" cell would silently borrow data
    from an unrelated column (e.g. picking up the dosage as the medicine
    name) instead of correctly treating the row as having no name.
    """
    for k in keys:
        if k in row and row[k] not in (None, ""):
            return str(row[k]).strip()
    if not any(k in row for k in keys):
        for v in row.values():
            if v not in (None, ""):
                return str(v).strip()
    return ""


# --------------------------------------------------------------------------
# Patients
# --------------------------------------------------------------------------

def get_all_patients() -> list[sqlite3.Row]:
    conn = get_conn()
    rows = conn.execute("SELECT * FROM patients ORDER BY last_name, first_name").fetchall()
    conn.close()
    return rows


def find_or_create_patient(
    first_name: str,
    middle_name: str | None,
    last_name: str,
    age: int | None,
    sex: str | None,
    address: str | None,
    civil_status: str | None,
) -> int:
    conn = get_conn()
    cur = conn.cursor()
    row = cur.execute(
        "SELECT * FROM patients WHERE first_name=? AND IFNULL(middle_name,'')=? AND last_name=?",
        (first_name, middle_name or "", last_name),
    ).fetchone()
    if row:
        cur.execute(
            """UPDATE patients SET age=?, sex=?, address=?, civil_status=?
               WHERE id=?""",
            (age, sex, address, civil_status, row["id"]),
        )
        conn.commit()
        pid = row["id"]
    else:
        cur.execute(
            """INSERT INTO patients (first_name, middle_name, last_name, age, sex, address, civil_status)
               VALUES (?,?,?,?,?,?,?)""",
            (first_name, middle_name, last_name, age, sex, address, civil_status),
        )
        conn.commit()
        pid = cur.lastrowid
    conn.close()
    return pid


# --------------------------------------------------------------------------
# Physicians
# --------------------------------------------------------------------------

def get_all_physicians() -> list[sqlite3.Row]:
    conn = get_conn()
    rows = conn.execute("SELECT * FROM physicians ORDER BY name").fetchall()
    conn.close()
    return rows


def find_or_create_physician(name: str, license_no: str | None, ptr_no: str | None, signature_path: str | None = None) -> int:
    name = ensure_dr_prefix(name)
    conn = get_conn()
    cur = conn.cursor()
    row = cur.execute("SELECT * FROM physicians WHERE name=?", (name,)).fetchone()
    if row:
        cur.execute(
            "UPDATE physicians SET license_no=?, ptr_no=?, signature_path=COALESCE(?, signature_path) WHERE id=?",
            (license_no, ptr_no, signature_path, row["id"]),
        )
        conn.commit()
        phid = row["id"]
    else:
        cur.execute(
            "INSERT INTO physicians (name, license_no, ptr_no, signature_path) VALUES (?,?,?,?)",
            (name, license_no, ptr_no, signature_path),
        )
        conn.commit()
        phid = cur.lastrowid
    conn.close()
    return phid


# --------------------------------------------------------------------------
# Medicines
# --------------------------------------------------------------------------

def get_all_medicines() -> list[sqlite3.Row]:
    conn = get_conn()
    rows = conn.execute("SELECT * FROM medicines ORDER BY name").fetchall()
    conn.close()
    return rows


def find_or_create_medicine(name: str, dosage: str | None, instructions: str | None) -> None:
    conn = get_conn()
    cur = conn.cursor()
    row = cur.execute("SELECT * FROM medicines WHERE name=?", (name,)).fetchone()
    if row:
        # new_dosage = row["default_dosage"] or dosage
        new_dosage = row["default_dosage"]  # Preserve existing data while dosage is disabled.
        new_instructions = row["default_instructions"] or instructions
        cur.execute(
            "UPDATE medicines SET default_dosage=?, default_instructions=? WHERE id=?",
            (new_dosage, new_instructions, row["id"]),
        )
        conn.commit()
    else:
        cur.execute(
            "INSERT INTO medicines (name, default_dosage, default_instructions) VALUES (?,?,?)",
            # (name, dosage, instructions),
            (name, None, instructions),
        )
        conn.commit()
    conn.close()


def bulk_import_medicines(file_path: str) -> tuple[int, int, int]:
    """Import many medicines at once from a CSV or Excel file.

    Recognized columns (case-insensitive): name/medicine/medicine_name,
    instructions/default_instructions/sig. Dosage columns are temporarily ignored.
    Returns (added, updated, skipped).
    """
    rows = _rows_from_tabular_file(file_path)

    added = updated = skipped = 0
    conn = get_conn()
    cur = conn.cursor()
    for row in rows:
        name = _pick(row, "name", "medicine", "medicine_name")
        if not name:
            skipped += 1
            continue
        # dosage = _pick(row, "dosage", "default_dosage")
        dosage = None  # Dosage import temporarily disabled.
        instructions = _pick(row, "instructions", "default_instructions", "sig")

        existing = cur.execute("SELECT * FROM medicines WHERE name=?", (name,)).fetchone()
        if existing:
            # new_dosage = existing["default_dosage"] or dosage
            new_dosage = existing["default_dosage"]  # Preserve existing data.
            new_instructions = existing["default_instructions"] or instructions
            if new_dosage != existing["default_dosage"] or new_instructions != existing["default_instructions"]:
                cur.execute(
                    "UPDATE medicines SET default_dosage=?, default_instructions=? WHERE id=?",
                    (new_dosage, new_instructions, existing["id"]),
                )
                updated += 1
        else:
            cur.execute(
                "INSERT INTO medicines (name, default_dosage, default_instructions) VALUES (?,?,?)",
                # (name, dosage, instructions),
                (name, None, instructions),
            )
            added += 1
    conn.commit()
    conn.close()
    return added, updated, skipped


# --------------------------------------------------------------------------
# Barangays / addresses
# --------------------------------------------------------------------------

def get_all_barangays() -> list[str]:
    """Return sorted list of barangay address strings (plus any used patient addresses)."""
    conn = get_conn()
    rows = conn.execute("SELECT name FROM barangays ORDER BY name").fetchall()
    names = [r["name"] for r in rows]
    # also include unique patient addresses not yet in the list
    patient_addrs = conn.execute(
        "SELECT DISTINCT address FROM patients WHERE address IS NOT NULL AND address != ''"
    ).fetchall()
    conn.close()
    seen = set(n.lower() for n in names)
    for r in patient_addrs:
        a = (r["address"] or "").strip()
        if a and a.lower() not in seen:
            names.append(a)
            seen.add(a.lower())
    return sorted(names, key=str.lower)


def add_barangay(name: str | None) -> None:
    """Remember a new address/barangay so it appears in autocomplete next time."""
    name = (name or "").strip()
    if not name:
        return
    conn = get_conn()
    conn.execute("INSERT OR IGNORE INTO barangays (name) VALUES (?)", (name,))
    conn.commit()
    conn.close()


def bulk_import_barangays(file_path: str) -> tuple[int, int]:
    """Import barangay names from CSV/Excel (column: name/address/barangay/location).

    Returns (added, skipped).
    """
    rows = _rows_from_tabular_file(file_path)

    added = skipped = 0
    conn = get_conn()
    cur = conn.cursor()
    for row in rows:
        name = _pick(row, "name", "address", "barangay", "barangay_name", "location")
        if not name:
            skipped += 1
            continue
        existing = cur.execute("SELECT id FROM barangays WHERE name=?", (name,)).fetchone()
        if existing:
            skipped += 1
        else:
            cur.execute("INSERT INTO barangays (name) VALUES (?)", (name,))
            added += 1
    conn.commit()
    conn.close()
    return added, skipped


# --------------------------------------------------------------------------
# Prescriptions
# --------------------------------------------------------------------------
def save_prescription(
    patient_id: int,
    physician_id: int,
    notes: str | None,
    items: list[dict[str, str]],
    date_issued: str | None = None,
) -> tuple[int, str]:
    conn = get_conn()
    cur = conn.cursor()
    if date_issued:
        parsed = parse_birthday(date_issued)  # reuses the flexible date parser
        date_issued = parsed.isoformat() if parsed else datetime.date.today().isoformat()
    else:
        date_issued = datetime.date.today().isoformat()
    cur.execute(
        "INSERT INTO prescriptions (patient_id, physician_id, date_issued, notes) VALUES (?,?,?,?)",
        (patient_id, physician_id, date_issued, notes),
    )
    prescription_id = cur.lastrowid
    for item in items:
        cur.execute(
            """INSERT INTO prescription_items (prescription_id, medicine_name, dosage, quantity, instructions)
               VALUES (?,?,?,?,?)""",
            # (prescription_id, item["name"], item["dosage"], item["quantity"], item["instructions"]),
            (prescription_id, item["name"], "", item["quantity"], item["instructions"]),
        )
    conn.commit()
    conn.close()
    return prescription_id, date_issued


def set_prescription_pdf_path(prescription_id: int, path: str) -> None:
    conn = get_conn()
    conn.execute("UPDATE prescriptions SET pdf_path=? WHERE id=?", (path, prescription_id))
    conn.commit()
    conn.close()


def get_prescription_full(prescription_id: int) -> tuple[sqlite3.Row, sqlite3.Row | None, sqlite3.Row | None, list[sqlite3.Row]]:
    conn = get_conn()
    presc = conn.execute("SELECT * FROM prescriptions WHERE id=?", (prescription_id,)).fetchone()
    patient = conn.execute("SELECT * FROM patients WHERE id=?", (presc["patient_id"],)).fetchone()
    physician = conn.execute("SELECT * FROM physicians WHERE id=?", (presc["physician_id"],)).fetchone()
    items = conn.execute(
        "SELECT * FROM prescription_items WHERE prescription_id=? ORDER BY id", (prescription_id,)
    ).fetchall()
    conn.close()
    return presc, patient, physician, items


def get_history(limit: int | None = None, *, patient_query: str = "", physician_query: str = "",
                date_from: str | None = None, date_to: str | None = None) -> list[sqlite3.Row]:
    """Search all saved prescriptions with literal, parameterized name filters."""
    clauses, values = [], []
    for token in patient_query.lower().split():
        clauses.append("instr(lower(pt.first_name || ' ' || COALESCE(pt.middle_name,'') || ' ' || pt.last_name), ?) > 0")
        values.append(token)
    for token in physician_query.lower().split():
        clauses.append("instr(lower(ph.name), ?) > 0")
        values.append(token)
    if date_from:
        clauses.append("p.date_issued >= ?"); values.append(date_from)
    if date_to:
        clauses.append("p.date_issued <= ?"); values.append(date_to)
    query = """SELECT p.id, p.date_issued, pt.first_name, pt.middle_name, pt.last_name,
               ph.name AS physician_name FROM prescriptions p
               JOIN patients pt ON pt.id = p.patient_id
               JOIN physicians ph ON ph.id = p.physician_id"""
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY p.date_issued DESC, p.id DESC"
    if limit is not None:
        query += " LIMIT ?"; values.append(limit)
    conn = get_conn()
    try:
        return conn.execute(query, values).fetchall()
    finally:
        conn.close()
