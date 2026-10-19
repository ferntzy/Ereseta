import sys,uuid,io
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from ereseta_local import config,database as db
from ereseta_local.app import EresetaApp
from ereseta_local.pdf_generator import prescription_pdf_bytes
from pypdf import PdfReader
root=Path(__file__).resolve().parent
config.DB_FILE=str(root/(uuid.uuid4().hex+'.db'));db.init_db()
app=EresetaApp();app.update()
try:
 assert not hasattr(app,'m_dosage')
 assert 'dosage' not in app.items_tree['columns']
 app.m_name.set('Test medicine');app.m_qty.insert(0,'5');app.m_instructions.insert(0,'Test instructions');app._add_item()
 assert app.items[0]['dosage']==''
 app.items_tree.selection_set(app.items_tree.get_children()[0]);app._edit_item();app._add_item()
 assert app.items_tree.item(app.items_tree.get_children()[0],'values')==('Test medicine','#5','Test instructions')
 patient=dict(first_name='Sample',middle_name='',last_name='Patient',age=20,sex='',civil_status='',address='')
 physician=dict(name='Dr. Sample',license_no='',ptr_no='',signature_path='')
 items=[dict(name='Test medicine',dosage='HIDDEN_DOSAGE',quantity='',instructions='Test instructions')]
 data=prescription_pdf_bytes(patient,physician,items)
 reader=PdfReader(io.BytesIO(data));reader.decrypt('');text=''.join(page.extract_text() for page in reader.pages)
 assert 'HIDDEN_DOSAGE' not in text and 'TEST MEDICINE' in text and 'Test instructions'.upper() in text
 db.find_or_create_medicine('Test medicine','HIDDEN_DOSAGE','Test instructions')
 assert not db.get_all_medicines()[0]['default_dosage']
 conn=db.get_conn();conn.execute("UPDATE medicines SET default_dosage='EXISTING' WHERE name='Test medicine'");conn.commit();conn.close()
 csv=root/'disabled-dosage.csv';csv.write_text('name,dosage,instructions\nTest medicine,REPLACEMENT,Test instructions\nNew medicine,IMPORTED,New instructions\n')
 db.bulk_import_medicines(str(csv))
 meds={r['name']:r for r in db.get_all_medicines()}
 assert meds['Test medicine']['default_dosage']=='EXISTING' and not meds['New medicine']['default_dosage']
 pid=db.find_or_create_patient('Sample','','Patient',20,'','','')
 did=db.find_or_create_physician('Sample','','','')
 rid,_=db.save_prescription(pid,did,'',items)
 assert not db.get_prescription_full(rid)[3][0]['dosage']
 app._clear_form();assert not app._has_draft()
 print('PASS: dosage UI removed, medicine editing works, PDF omits dosage, imports and saves ignore dosage, existing data preserved')
finally:app.destroy()
