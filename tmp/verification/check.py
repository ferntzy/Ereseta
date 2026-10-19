import sys
sys.path.insert(0, r'C:\Users\OWNER\Desktop\ereseta')
import os, sqlite3, datetime, uuid
from pathlib import Path
from unittest.mock import patch
from PIL import Image, ImageDraw
from ereseta_local import config, database as db
from ereseta_local.pdf_generator import generate_pdf
from ereseta_local.app import EresetaApp
root=Path('tmp/verification').resolve()
config.DB_FILE=str(root/(uuid.uuid4().hex+'.db')); config.OUTPUT_DIR=str(root)
# Start with the existing birthday-only schema to exercise migration.
conn=sqlite3.connect(config.DB_FILE)
conn.execute('CREATE TABLE IF NOT EXISTS patients (id INTEGER PRIMARY KEY, first_name TEXT, middle_name TEXT, last_name TEXT, birthday TEXT, sex TEXT, address TEXT, civil_status TEXT)')
conn.execute("INSERT OR REPLACE INTO patients VALUES (1,'Legacy','','Patient','01/01/1990','Female','Test address','Single')")
conn.commit();conn.close()
db.init_db(); db.init_db()
assert db.get_all_patients()[0]['age']==datetime.date.today().year-1990
pid=db.find_or_create_patient('Test','','Patient',0,'Female','Test address','Single')
assert next(p for p in db.get_all_patients() if p['id']==pid)['age']==0
sig=root/'signature.png'; im=Image.new('RGBA',(300,90),'white');ImageDraw.Draw(im).text((20,30),'TEST SIGNATURE',fill='black');im.save(sig)
ph=db.find_or_create_physician('Test Doctor','123','456',str(sig))
other=db.find_or_create_physician('Other Doctor','','','')
assert db.get_all_physicians()[1]['signature_path']==str(sig)
db.find_or_create_physician('Test Doctor','123','456','')
assert db.get_all_physicians()[1]['signature_path']==''
db.find_or_create_physician('Test Doctor','123','456',str(sig))
rx,_=db.save_prescription(pid,ph,'Return for follow-up in one week.',[dict(name='TEST MEDICINE',dosage='',quantity='10',instructions='Sample instructions')])
path=generate_pdf(rx); (root/'pdf_path.txt').write_text(path)
app=EresetaApp();app.withdraw()
app.p_picker.set('Test Patient');app._on_patient_picked();assert app.p_age.get()=='0'
app.ph_name.set('Dr. Test Doctor');app._on_physician_picked();assert app.ph_signature.get()==str(sig)
app.ph_name.set('Dr. Other Doctor');app._on_physician_picked();assert app.ph_signature.get()==''
with patch('ereseta_local.app.messagebox.showwarning'):
 for bad in ['', '-1', '1.5', 'abc','131']:
  app.p_age.delete(0,'end');app.p_age.insert(0,bad);assert app._read_age() is None
app._clear_form();assert app.p_age.get()=='' and app.ph_signature.get()==''
app.destroy()
print('PASS: legacy migration, age zero, validation, signature assign/remove/switch, clear form, PDF generation')


