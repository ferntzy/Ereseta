import sys, uuid, io
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from ereseta_local import config,database as db
from ereseta_local.app import EresetaApp
from ereseta_local.formatting import format_quantity
from ereseta_local.pdf_generator import prescription_pdf_bytes
from pypdf import PdfReader
root=Path(__file__).resolve().parent
config.DB_FILE=str(root/(uuid.uuid4().hex+'.db'));db.init_db()
app=EresetaApp();app.update()
errors=[];app.report_callback_exception=lambda *args:errors.append(args)
try:
 assert all(x in config.CIVIL_STATUS_OPTIONS for x in ['Child','Widower','Other'])
 app.p_civil.set('Other');app._civil_status_changed();app.update()
 assert app.civil_other_frame.winfo_ismapped()
 with patch('ereseta_local.app.messagebox.showwarning') as warning:
  assert app._read_civil_status() is None;assert warning.called
 app.p_civil_other.insert(0,'Custom status')
 app.p_first.insert(0,'Sample');app.p_last.insert(0,'Patient');app.p_age.insert(0,'30')
 with patch('ereseta_local.app.messagebox.showinfo'):app._save_patient_record()
 patient=next(iter(db.get_all_patients()));assert patient['civil_status']=='Custom status'
 app._set_civil_status('Child');app.update();assert not app.civil_other_frame.winfo_ismapped()
 app.p_picker.set(db.full_name(patient));app._on_patient_picked()
 assert app.p_civil.get()=='Other' and app._read_civil_status()=='Custom status'
 app.m_qty.insert(0,'1 ');app.m_qty.insert('end','bottle');assert app.m_qty.get()=='1 bottle';app.m_qty.delete(0,'end')
 app.ph_name.set('Sample Doctor')
 for name,qty in [('Empty',''),('Number','10'),('Prefixed','#5'),('Duplicate','##7')]:
  app.m_name.set(name);app.m_qty.insert(0,qty);app._add_item()
 assert [app.items_tree.item(row,'values')[2] for row in app.items_tree.get_children()]==['#','#10','#5','#7']
 draft=app._collect_draft();assert draft['patient']['civil_status']=='Custom status'
 pdf=prescription_pdf_bytes(draft['patient'],draft['physician'],draft['items'],template=draft['template'])
 reader=PdfReader(io.BytesIO(pdf));reader.decrypt('');text='\n'.join(p.extract_text() for p in reader.pages)
 assert sum(line.startswith('#') for line in text.splitlines())==4,text
 assert '\n#\n' in text and '#10' in text and '#5' in text and '#7' in text,text
 assert 'CUSTOM STATUS' in text.upper()
 physician=db.find_or_create_physician('Sample Doctor','','','')
 saved,_=db.save_prescription(patient['id'],physician,'',app.items)
 app._refresh_history();app._clear_form();app.history_tree.selection_set(str(saved))
 with patch('ereseta_local.app.messagebox.showinfo'):app._reuse_prescription()
 assert app.p_civil.get()=='Other' and app.p_civil_other.get()=='Custom status'
 app._clear_form();app.update();assert not app.p_civil_other.get() and not app.civil_other_frame.winfo_ismapped() and not app._has_draft()
 assert format_quantity(None)=='#' and format_quantity(' # #12 ')=='#12'
 assert not errors,errors
 print('PASS: civil options, Other validation/save/load/reuse/reset, quantity entry/table/PDF including blank and duplicate prefixes')
finally:app.destroy()

