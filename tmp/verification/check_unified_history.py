import sys,uuid,io,copy
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from ereseta_local import config,database as db
from ereseta_local.opd_database import unified_history,get_opd,export_opd
from ereseta_local.opd_pdf import opd_pdf_bytes
from ereseta_local.app import EresetaApp
from pypdf import PdfReader
from PIL import Image,ImageDraw
import pypdfium2 as pdfium
root=Path(__file__).resolve().parent;config.DB_FILE=str(root/(uuid.uuid4().hex+'.db'));config.OUTPUT_DIR=str(root);db.init_db()
sig=root/'opd-test-signature.png';im=Image.new('RGBA',(200,60),(0,0,0,0));d=ImageDraw.Draw(im);d.line([(10,50),(50,10),(70,45),(170,15)],fill='black',width=3);im.save(sig)
did=db.find_or_create_physician('Example','','',str(sig));pid=db.find_or_create_patient('Sample','','Patient',30,'Female','','Single')
rid,_=db.save_prescription(pid,did,'',[dict(name='Test',dosage='',quantity='1',instructions='')],date_issued='2026-10-14')
app=EresetaApp();app.update();errors=[];app.report_callback_exception=lambda *a:errors.append(a)
try:
 ed=app.opd_editor;ed.fill_patient(dict(first_name='Sample',last_name='Patient',age=30,address='Test address'));ed.doctor.set('Dr. Example');ed.fields['hospital_no'].insert(0,'HN001');ed.date.set('10/14/2026')
 ed.soap['P'].insert('1.0','Plan details')
 draft=ed.collect();assert not draft['include_signature']
 no_signature=opd_pdf_bytes(draft)
 draft['include_signature']=True;pdf=opd_pdf_bytes(draft)
 assert pdf!=no_signature
 reader=PdfReader(io.BytesIO(pdf));reader.decrypt('');assert len(reader.pages)==1;assert 'Dr. Example' in reader.pages[0].extract_text()
 doc=pdfium.PdfDocument(pdf);page=doc[0];bitmap=page.render(scale=1.2);bitmap.to_pil().save(root/'opd-doctor.png');bitmap.close();page.close();doc.close()
 with patch('ereseta_local.opd_editor.messagebox.askyesno',return_value=False):ed.save(draft,pdf)
 assert (root/'OPD_00001.pdf').read_bytes()==pdf
 assert get_opd(1)['pdf']==pdf
 app._refresh_history();assert set(app.history_tree.get_children())=={'Prescription:1','OPD:1'}
 assert len(unified_history(physician_query='example'))==2
 assert len(unified_history(kind='OPD',hospital_query='HN001',date_from='2026-10-14',date_to='2026-10-14'))==1
 assert not unified_history(date_from='2027-01-01')
 app.history_type.set('OPD');app._refresh_history();assert app.history_tree.get_children()==('OPD:1',)
 app.history_tree.selection_set('OPD:1')
 with patch('ereseta_local.app.open_file') as opened:app._open_selected_history_pdf();assert opened.called
 app._reuse_prescription();assert ed.doctor.get()=='Dr. Example' and not ed.include_signature.get()
 ed.doctor.set('Unknown doctor');ed.include_signature.set(True)
 try:ed.collect()
 except ValueError as exc:assert 'signature' in str(exc)
 else:raise AssertionError('Missing signature accepted')
 ed.clear(confirm=False);app._clear_history_filters();app.history_tree.selection_set('Prescription:1')
 with patch('ereseta_local.app.messagebox.showinfo'):app._reuse_prescription()
 assert app.p_first.get()=='Sample'
 assert not errors,errors
 print('PASS: optional doctor signature, PDF exported on save, unified IDs/filters, correct OPD opening/reuse and prescription reuse')
finally:app.destroy()
