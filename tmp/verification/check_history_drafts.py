import sys,uuid,datetime
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from PIL import ImageChops,ImageGrab
import pypdfium2 as pdfium
from ereseta_local import config,database as db
from ereseta_local.app import EresetaApp
from ereseta_local.pdf_generator import prescription_pdf_bytes
root=Path(__file__).resolve().parent
config.DB_FILE=str(root/(uuid.uuid4().hex+'.db'));config.OUTPUT_DIR=str(root);db.init_db()
p1=db.find_or_create_patient('Alice','','Example',35,'Female','Address','Single')
p2=db.find_or_create_patient('Bob','','Percent%',48,'Male','Other address','Married')
d1=db.find_or_create_physician('Alpha','L1','P1','');d2=db.find_or_create_physician('Beta','L2','P2','')
items=[dict(name='TEST MEDICINE',dosage='10 mg',quantity='5',instructions='Sample instructions')]
source,_=db.save_prescription(p1,d1,'Source notes',items,date_issued='2026-01-15')
for _ in range(204):db.save_prescription(p2,d2,'Other',items,date_issued='2026-09-20')
assert len(db.get_history())==205
assert len(db.get_history(patient_query='example alice',physician_query='alpha',date_from='2026-01-15',date_to='2026-01-15'))==1
assert len(db.get_history(patient_query='%'))==204
assert not db.get_history(physician_query="' OR 1=1 --")
app=EresetaApp();app.update();errors=[];app.report_callback_exception=lambda *args:errors.append(args)
def settle():app.after(300,app.quit);app.mainloop();app.update()
def snapshot():
 c=db.get_conn();result=list(c.iterdump());c.close();return result
warnings=[]
def raster(data):
 doc=pdfium.PdfDocument(data);page=doc[0];bitmap=page.render(scale=1);image=bitmap.to_pil().copy();bitmap.close();page.close();doc.close();return image
try:
 app.history_patient.set('Alice');app.history_doctor.set('Alpha');app.history_from.set('01/15/2026');app.history_to.set('01/15/2026');app._refresh_history()
 assert app.history_tree.get_children()==(str(source),)
 app.history_from.set('02/01/2026');app._refresh_history();assert 'From date' in app.history_status.get()
 app._clear_history_filters();assert len(app.history_tree.get_children())==205
 app.history_tree.selection_set(str(source));before=snapshot()
 with patch('ereseta_local.app.messagebox.showinfo'):
  app._reuse_prescription()
 assert snapshot()==before,'reuse must not save'
 assert app.p_first.get()=='Alice' and app.notes_entry.get()=='Source notes' and app.items==items
 assert db.parse_birthday(app.rx_date.get())==datetime.date.today()
 # Refusing draft replacement keeps the current form.
 app.notes_entry.delete(0,'end');app.notes_entry.insert(0,'Edited notes')
 with patch('ereseta_local.app.messagebox.askyesno',return_value=False):app._reuse_prescription()
 assert app.notes_entry.get()=='Edited notes'
 before=snapshot();app._open_pdf_editor();settle();preview=app.draft_preview
 assert preview.winfo_exists() and snapshot()==before,'preview must not write any records'
 assert 'Page 1' in preview.page_label.get()
 preview.destroy();assert app.p_first.get()=='Alice' and app.notes_entry.get()=='Edited notes'
 # Invalid date blocks both preview and direct save.
 app.rx_date._var.set('bad')
 with patch('ereseta_local.app.messagebox.showwarning',side_effect=lambda *args:warnings.append(args)):
  assert app._collect_draft() is None
 assert warnings;app.rx_date.set(datetime.date.today())
 draft=app._collect_draft();preview_bytes=prescription_pdf_bytes(draft['patient'],draft['physician'],draft['items'],notes=draft['notes'],date_issued=draft['date'],template=draft['template'])
 app._open_pdf_editor();settle()
 with patch('ereseta_local.app.messagebox.askyesno',return_value=False):app.draft_preview._save()
 assert len(db.get_history())==206 and not app.draft_preview.winfo_exists()
 old=db.get_prescription_full(source);assert old[0]['notes']=='Source notes' and old[3][0]['medicine_name']=='TEST MEDICINE'
 latest=db.get_prescription_full(db.get_history()[0]['id']);assert latest[0]['notes']=='Edited notes'
 assert ImageChops.difference(raster(preview_bytes).convert('RGB'),raster(Path(latest[0]['pdf_path']).read_bytes()).convert('RGB')).getbbox() is None
 # Reuse again and verify all pages can be reviewed in a long draft.
 app.history_tree.selection_set(str(source))
 with patch('ereseta_local.app.messagebox.showinfo'):app._reuse_prescription()
 app.items=items*45;app._open_pdf_editor();settle();preview=app.draft_preview
 assert len(preview._document)>1;preview._turn(1);assert preview._page==1;preview._turn(-1);assert preview._page==0
 preview.destroy()
 app.notebook.select(app.history_tab);app.geometry('860x660');app.attributes('-topmost',True);app.lift();settle()
 ImageGrab.grab(bbox=(app.winfo_rootx(),app.winfo_rooty(),app.winfo_rootx()+app.winfo_width(),app.winfo_rooty()+app.winfo_height())).save(root/'history-search.png')
 assert not errors,errors
 print('PASS: all-history search over 200 records, patient/doctor/date combinations, literal searches, invalid ranges, reuse without saving, overwrite cancellation, preview without writes, date validation, save once, old items/notes retained, preview/final pixel equality, multipage navigation')
finally:app.destroy()
