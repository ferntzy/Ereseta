import sys, uuid, types
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from ereseta_local import config, database as db
from ereseta_local.app import EresetaApp
root=Path(__file__).resolve().parent
config.DB_FILE=str(root/(uuid.uuid4().hex+'.db'))
db.init_db()
app=EresetaApp(); app.update()
errors=[]
app.report_callback_exception=lambda *args: errors.append(args)
box=app.m_name
# Scroll the medicine field into view before interacting.
canvas=box.master.master.master.master.master
# Find its enclosing Canvas without depending on the exact frame nesting.
parent=box
while parent.winfo_class()!='Canvas': parent=parent.master
parent.yview_moveto(.48);app.update()
app.focus_force();box.focus_set();app.update()
box.set_completion_list(['Paracetamol 500 mg','Paracetamol syrup','Amoxicillin 500 mg'])
def type_text(text):
 box.set('');box.insert(0,text);app.update()
def visible(): return box._suggestion_window is not None
try:
 type_text('Para');assert visible(), 'typing should open suggestions'
 assert box._listbox.size()==2
 assert box.get()=='Para'
 box.event_generate('<Escape>');app.update();assert not visible() and box.get()=='Para'
 type_text('Para');app.m_qty.focus_set();app.update();assert not visible(), 'focus-out must dismiss'
 box.focus_set();app.update();type_text('Para')
 app.event_generate('<ButtonPress-1>',x=5,y=5);app.update();assert not visible(), 'outside click must dismiss'
 type_text('BrandNewMedicineXYZ');assert not visible() and box.get()=='BrandNewMedicineXYZ'
 type_text('Para');box.event_generate('<Down>');box.event_generate('<Return>');app.update()
 assert box.get()=='Paracetamol syrup' and not visible(), 'keyboard selection'
 type_text('Para');box._listbox.event_generate('<ButtonPress-1>',x=8,y=8);app.update()
 assert box.get()=='Paracetamol syrup' and not visible(), 'mouse selection'
 type_text('Para');box.event_generate('<Tab>');app.update();assert not visible(), 'Tab dismissal'
 box.focus_set();app.update();type_text('Para');box.set('');app.update();assert not visible(), 'reset cancels popup'
 box.insert(0,'Para');box._hide_suggestions();app.update();assert not visible(), 'pending job cancelled'
 type_text('Para');parent.yview_scroll(2,'units');app.update();assert not visible(), 'scroll dismissal'
 # Arrow button uses the same dropdown, and pasted text is filtered.
 box.focus_set();app.update();box.set('Para')
 box.event_generate('<ButtonPress-1>',x=box.winfo_width()-5,y=box.winfo_height()//2);app.update()
 assert visible(), 'arrow opens filtered dropdown'
 box.event_generate('<ButtonPress-1>',x=box.winfo_width()-5,y=box.winfo_height()//2);app.update()
 assert not visible(), 'arrow toggles closed'
 box.clipboard_clear();box.clipboard_append('Amox');box.set('');box.event_generate('<<Paste>>');app.update()
 assert visible() and box._listbox.size()==1, 'paste filtering'
 box.delete(0,'end');app.update();assert not visible(), 'empty input closes suggestions'
 # Check right-edge clipping at the supported minimum width.
 app.geometry('860x660');app.update()
 for widget in (app.p_first, app.p_last, app.p_civil, app.ph_ptr, app.m_qty, app.rx_date):
  assert widget.winfo_rootx()+widget.winfo_width() <= app.winfo_rootx()+app.winfo_width(), str(widget)
 assert not errors, errors
 from PIL import ImageGrab
 app.geometry('1080x820');parent.yview_moveto(0);app.update()
 app.after(200,app.quit);app.mainloop()
 ImageGrab.grab(bbox=(app.winfo_rootx(),app.winfo_rooty(),app.winfo_rootx()+app.winfo_width(),app.winfo_rooty()+app.winfo_height())).save(root/'form-top.png')
 parent.yview_moveto(1);app.update();app.after(200,app.quit);app.mainloop()
 ImageGrab.grab(bbox=(app.winfo_rootx(),app.winfo_rooty(),app.winfo_rootx()+app.winfo_width(),app.winfo_rooty()+app.winfo_height())).save(root/'form-bottom.png')
 print('PASS: live filtering, free text, mouse and keyboard selection, Escape/Tab/focus/outside click/scroll/reset dismissal, minimum-width layout')
finally:
 app.destroy()


