import sys,uuid
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from PIL import ImageGrab
from ereseta_local import config,database as db
from ereseta_local.app import EresetaApp
root=Path(__file__).resolve().parent
config.DB_FILE=str(root/(uuid.uuid4().hex+'.db'));db.init_db()
app=EresetaApp();app.geometry('860x660');app.update()
errors=[];app.report_callback_exception=lambda *args:errors.append(args)
def settle():app.after(150,app.quit);app.mainloop();app.update()
try:
 app.m_name.set('First medicine');app.m_qty.insert(0,'3');app._add_item()
 app.m_name.set('Second medicine');app._add_item()
 original=[dict(x) for x in app.items]
 app.items_tree.selection_set(app.items_tree.get_children()[0]);app._edit_item()
 assert app.items==original,'editing must not remove original'
 app.m_name.set('Changed');app._cancel_item_edit();assert app.items==original
 app.items_tree.selection_set(app.items_tree.get_children()[0]);app._edit_item();app.m_name.set('Changed');app._add_item()
 assert [i['name'] for i in app.items]==['Changed','Second medicine']
 app.items_tree.selection_set(app.items_tree.get_children());app._remove_item();assert not app.items
 app._undo_remove();assert [i['name'] for i in app.items]==['Changed','Second medicine']
 with patch('ereseta_local.app.messagebox.askyesno',return_value=False):app._confirm_exit()
 assert app.winfo_exists()
 with patch('ereseta_local.app.messagebox.showwarning'):
  assert app._collect_draft() is None
 assert app.focus_get()==app.p_first or app.p_first.winfo_ismapped()
 app._focus_field(app.m_name);app.update()
 canvas=app._page_canvases[str(app.new_rx_tab)]
 assert app.m_name.winfo_rooty()>=canvas.winfo_rooty()
 assert app.m_name.winfo_rooty()+app.m_name.winfo_height()<=canvas.winfo_rooty()+canvas.winfo_height()
 app._clear_form();assert not app.items and app._editing_item is None and not app._has_draft()
 app.geometry('1080x820');app.attributes('-topmost',True);app.lift();app.focus_force();app._focus_field(app.p_picker);settle()
 ImageGrab.grab(bbox=(app.winfo_rootx(),app.winfo_rooty(),app.winfo_rootx()+app.winfo_width(),app.winfo_rooty()+app.winfo_height())).save(root/'friendly-form.png')
 app._focus_field(app.m_name);settle()
 ImageGrab.grab(bbox=(app.winfo_rootx(),app.winfo_rooty(),app.winfo_rootx()+app.winfo_width(),app.winfo_rooty()+app.winfo_height())).save(root/'friendly-medicines.png')
 assert not errors,errors
 print('PASS: non-destructive medicine editing/cancel, stable order, undo multi-remove, close protection, required field guidance, section navigation, clear form')
finally:app.destroy()
