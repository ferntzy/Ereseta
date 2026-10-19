"""OPD storage uses the application's existing SQLite database."""
import datetime
import json
import os
from . import config
from contextlib import closing
from .database import get_conn


def init_opd_schema():
    with closing(get_conn()) as conn, conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS opd_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER NOT NULL REFERENCES patients(id),
            date_issued TEXT NOT NULL,
            patient_name TEXT NOT NULL,
            hospital_no TEXT NOT NULL DEFAULT '',
            payload TEXT NOT NULL,
            pdf BLOB NOT NULL,
            created_at TEXT NOT NULL
        )''')
        conn.execute('CREATE INDEX IF NOT EXISTS opd_date ON opd_records(date_issued)')


def save_opd(draft, pdf):
    """Save patient and immutable visit/PDF snapshots in one transaction."""
    p = draft['patient']
    with closing(get_conn()) as conn, conn:
        row = conn.execute("SELECT id FROM patients WHERE first_name=? AND IFNULL(middle_name,'')=? AND last_name=?",
                           (p['first_name'], p.get('middle_name',''), p['last_name'])).fetchone()
        if row:
            patient_id = row['id']
            # OPD has no sex/civil status fields: preserve those existing values.
            conn.execute('UPDATE patients SET age=?, address=? WHERE id=?', (p['age'],p['address'],patient_id))
        else:
            patient_id = conn.execute('INSERT INTO patients(first_name,middle_name,last_name,age,address) VALUES(?,?,?,?,?)',
                (p['first_name'],p.get('middle_name',''),p['last_name'],p['age'],p['address'])).lastrowid
        doctor=draft.get('physician',{}).get('name','')
        if doctor:
            conn.execute('INSERT OR IGNORE INTO physicians(name) VALUES(?)',(doctor,))
        record_id = conn.execute('INSERT INTO opd_records(patient_id,date_issued,patient_name,hospital_no,payload,pdf,created_at) VALUES(?,?,?,?,?,?,?)',
            (patient_id,draft['date'], ' '.join(filter(None,[p['first_name'],p.get('middle_name',''),p['last_name']])),
             draft['hospital_no'],json.dumps(draft),pdf,datetime.datetime.now().isoformat())).lastrowid
        conn.execute('INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)', ('opd_page',json.dumps(draft['page'])))
        return record_id


def list_opd(query=''):
    # Search snapshots, so later patient edits cannot rename old visits.
    with closing(get_conn()) as conn:
        return conn.execute('''SELECT id,date_issued,patient_name,hospital_no FROM opd_records
            WHERE instr(lower(patient_name || ' ' || hospital_no || ' ' || date_issued),lower(?)) > 0
            ORDER BY date_issued DESC,id DESC''', (query.strip(),)).fetchall()


def get_opd(record_id):
    with closing(get_conn()) as conn:
        row = conn.execute('SELECT * FROM opd_records WHERE id=?',(record_id,)).fetchone()
        if row is None: raise ValueError('This OPD record no longer exists.')
        return dict(row)


def export_opd(record_id):
    row = get_opd(record_id)
    os.makedirs(config.OUTPUT_DIR, exist_ok=True)
    path = os.path.join(config.OUTPUT_DIR, f'OPD_{record_id:05d}.pdf')
    temporary = path + '.tmp'
    with open(temporary, 'wb') as output:
        output.write(row['pdf'])
    os.replace(temporary, path)
    return path


def unified_history(patient_query='', physician_query='', date_from=None, date_to=None, kind='All', hospital_query=''):
    from .database import get_history, full_name
    rows = []
    if kind in ('All', 'Prescription') and not hospital_query.strip():
        for row in get_history(patient_query=patient_query, physician_query=physician_query, date_from=date_from, date_to=date_to):
            rows.append(dict(id=row['id'], kind='Prescription', date=row['date_issued'], patient=full_name(row), doctor=row['physician_name'], hospital=''))
    if kind in ('All', 'OPD'):
        with closing(get_conn()) as conn:
            for row in conn.execute('SELECT id,date_issued,patient_name,hospital_no,payload FROM opd_records'):
                draft=json.loads(row['payload']);doctor=draft.get('physician',{}).get('name','')
                if any(word not in row['patient_name'].casefold() for word in patient_query.casefold().split()):continue
                if any(word not in doctor.casefold() for word in physician_query.casefold().split()):continue
                if hospital_query.casefold().strip() not in row['hospital_no'].casefold():continue
                if date_from and row['date_issued']<date_from:continue
                if date_to and row['date_issued']>date_to:continue
                rows.append(dict(id=row['id'],kind='OPD',date=row['date_issued'],patient=row['patient_name'],doctor=doctor,hospital=row['hospital_no']))
    return sorted(rows,key=lambda r:(r['date'],r['id'],r['kind']),reverse=True)
