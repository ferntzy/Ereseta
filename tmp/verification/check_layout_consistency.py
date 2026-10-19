import sys,uuid
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from ereseta_local import config,database as db
from ereseta_local.app import EresetaApp
from PIL import ImageGrab
root=Path(__file__).resolve().parent;config.DB_FILE=str(root/(uuid.uuid4().hex+'.db'));config.OUTPUT_DIR=str(root);db.init_db()
app=EresetaApp();app.update();errors=[];app.report_callback_exception=lambda *a:errors.append(a)
def settle():app.after(350,app.quit);app.mainloop();app.update()
try:
 rx=app.template_editor;opd=app.opd_layout_editor
 before=db.get_setting('template');rx.body_font_var.set(10)
 with patch('ereseta_local.template_editor.open_file'):rx._preview_pdf()
 assert db.get_setting('template')==before and rx.dirty
 before_opd=db.get_setting('opd_layout');opd.values['body_size'].set(11)
 with patch('ereseta_local.opd_layout_editor.open_file'):opd.print_preview()
 assert db.get_setting('opd_layout')==before_opd and opd.dirty
 with patch('ereseta_local.opd_layout_editor.messagebox.askyesno',return_value=False):opd.defaults()
 assert opd.values['body_size'].get()=='11'
 rx._save_template();opd.save();assert not rx.dirty and not opd.dirty
 app.notebook.select(app.template_tab);app.layout_tabs.select(0);settle();rx.zoom_signature();settle();assert rx.zoom_var.get()=='200%'
 app.layout_tabs.select(app.opd_layout_panel);settle();opd.zoom_signature();settle();assert opd.zoom.get()=='200%'
 opd.nudge_signature(-.01,0);assert opd.signature_position['signature_x'] is not None
 opd.resize_signature(.9);assert float(opd.values['signature_width'].get())==135
 opd.preview_doctor.set('Current record doctor');settle();assert opd.photo is not None
 app.geometry('860x660');app.attributes('-topmost',True);app.lift();app.focus_force();settle();ImageGrab.grab(bbox=(app.winfo_rootx(),app.winfo_rooty(),app.winfo_rootx()+app.winfo_width(),app.winfo_rooty()+app.winfo_height())).save(root/'layout-consistency.png')
 assert opd.canvas.winfo_width()>=300,opd.canvas.winfo_width()
 app.layout_tabs.select(0);settle();assert rx.preview_canvas.winfo_width()>=300
 assert not errors,errors
 print('PASS: previews do not save, explicit saving/dirty flags, reset cancellation, matching zoom, OPD nudge/resize/doctor selection')
finally:app.destroy()
