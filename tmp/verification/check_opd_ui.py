import sys,uuid
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from ereseta_local import config,database as db
from ereseta_local.app import EresetaApp
from ereseta_local.opd_database import list_opd
from PIL import ImageGrab
root=Path(__file__).resolve().parent;config.DB_FILE=str(root/(uuid.uuid4().hex+'.db'));db.init_db()
app=EresetaApp();app.geometry('1080x820');app.update();errors=[];app.report_callback_exception=lambda *args:errors.append(args)
try:
 editor=app.opd_editor;app.notebook.select(app.opd_tab);app.update()
 assert not editor.has_draft()
 editor.fill_patient(dict(first_name='Sample',last_name='Patient',age=21,address='Sample address'))
 editor.soap['P'].insert('1.0','Plan example')
 draft=editor.collect();assert draft['page']==dict(width=8.5,height=11)
 editor.preview();app.update();preview=editor.preview_window
 assert preview.title().startswith('Review OPD') and not list_opd()
 preview.destroy();editor.preview();app.update();editor.preview_window._save();app.update()
 assert len(list_opd())==1 and not editor.has_draft() and len(db.get_all_patients())==1
 editor.fill_patient(dict(first_name='Sample',last_name='Patient',age=21,address='Sample address'))
 with patch('ereseta_local.app.messagebox.askyesno',return_value=False):app._confirm_exit()
 assert app.winfo_exists()
 editor.clear(confirm=False)
 editor.width.set('nan')
 try:editor.collect()
 except ValueError:pass
 else:raise AssertionError('Invalid input accepted')
 editor.width.set('8.5')
 app.attributes('-topmost',True);app.lift();app.update();app.after(100,app.quit);app.mainloop()
 ImageGrab.grab(bbox=(app.winfo_rootx(),app.winfo_rooty(),app.winfo_rootx()+app.winfo_width(),app.winfo_rooty()+app.winfo_height())).save(root/'opd-ui.png')
 app.geometry('860x660');app.update()
 canvas=app._page_canvases[str(app.opd_tab)];before=canvas.yview();editor.fields['first_name'].event_generate('<MouseWheel>',delta=-120);app.update();assert canvas.yview()!=before
 assert not errors,errors
 print('PASS: OPD tab, preview without saving, save/reset/shared patients, exit protection, small-window scrolling')
finally:app.destroy()
