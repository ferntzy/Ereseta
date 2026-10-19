import sys,uuid,io
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from ereseta_local import config,database as db
from ereseta_local.app import EresetaApp
from ereseta_local.opd_pdf import opd_pdf_bytes
from pypdf import PdfReader
from PIL import ImageGrab
root=Path(__file__).resolve().parent;config.DB_FILE=str(root/(uuid.uuid4().hex+'.db'));config.OUTPUT_DIR=str(root);db.init_db()
app=EresetaApp();app.geometry('1080x820');app.update();errors=[];app.report_callback_exception=lambda *a:errors.append(a)
def settle():app.after(400,app.quit);app.mainloop();app.update()
def shot(name):
 app.lift();app.attributes('-topmost',True);settle();ImageGrab.grab(bbox=(app.winfo_rootx(),app.winfo_rooty(),app.winfo_rootx()+app.winfo_width(),app.winfo_rooty()+app.winfo_height())).save(root/name)
try:
 editor=app.opd_layout_editor;app.opd_editor.open_layout();settle()
 assert editor.photo is not None
 before=db.get_setting('template')
 editor.values['title'].set('OUTPATIENT CLINICAL RECORD');editor.values['doctor_position'].set('Left');editor.values['p_weight'].set('Large')
 editor.values['body_size'].set('11');editor.save();assert not editor.dirty
 assert db.get_setting('template')==before
 assert db.get_setting('opd_layout')['doctor_position']=='Left'
 ed=app.opd_editor;ed.fill_patient(dict(first_name='Test',last_name='Patient',age=30,address='Example'));ed.doctor.set('Test doctor')
 draft=ed.collect();assert draft['opd_layout']['body_size']==11
 pdf=opd_pdf_bytes(draft);reader=PdfReader(io.BytesIO(pdf));reader.decrypt('');assert 'OUTPATIENT CLINICAL RECORD' in reader.pages[0].extract_text()
 (root/'opd-custom-layout.pdf').write_bytes(pdf)
 shot('opd-layout-editor.png')
 editor.values['margin'].set('nan')
 with patch('ereseta_local.opd_layout_editor.messagebox.showwarning') as warn:editor.save();assert warn.called
 assert db.get_setting('opd_layout')['margin']==.45
 editor.defaults();editor.save()
 app.notebook.select(app.opd_tab);ed.focus_field(ed.soap['P']);settle();assert ed.soap_tabs.select()==str(ed.soap_panels['P'])
 shot('opd-simple-notes.png')
 app.notebook.select(app.history_tab);shot('history-simple.png')
 app.geometry('860x660');ed.open_layout();settle();assert editor.photo is not None
 assert not errors,errors
 print('PASS: saved OPD layout affects real PDFs; prescription settings unchanged; validation; SOAP navigation; preview and small window')
finally:app.destroy()
