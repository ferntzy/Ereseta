import sys, uuid
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import tkinter as tk
from tkinter import ttk
from ereseta_local import config, database as db
from ereseta_local.app import EresetaApp
root=Path(__file__).resolve().parent
config.DB_FILE=str(root/(uuid.uuid4().hex+'.db'));db.init_db()
app=EresetaApp();app.geometry('860x660');app.update()
errors=[];app.report_callback_exception=lambda *args: errors.append(args)
def wheel(widget,delta=-120):
 widget.event_generate('<MouseWheel>',delta=delta);app.update()
def select(tab):
 app.notebook.select(tab);app.update()
rx=app._page_canvases[str(app.new_rx_tab)]
history=app._page_canvases[str(app.history_tab)]
outer=app._page_canvases[str(app.template_tab)]
settings=app.template_editor.settings_canvas
try:
 before=settings.yview();wheel(app.p_first)
 assert rx.yview()[0]>0, 'New Prescription entry must scroll its page'
 assert settings.yview()==before, 'hidden Template Editor must not scroll'
 app.p_sex.set('Female');old=rx.yview();wheel(app.p_sex)
 assert app.p_sex.get()=='Female' and rx.yview()[0]>old[0], 'wheel must not change selection'
 rx.yview_moveto(0);app.update();wheel(rx)
 assert rx.yview()[0]>0, 'blank canvas scrolling'
 rx.yview_moveto(0);app.update();app._wheel_remainder=0
 for _ in range(4):wheel(app.p_first,-10)
 assert rx.yview()[0]>0, 'small touchpad deltas'
 for i in range(100):app.history_tree.insert('', 'end',values=(i,'2026-09-29','Test patient','Test doctor'))
 select(app.history_tab);saved_rx=rx.yview();saved_settings=settings.yview()
 wheel(app.history_tree)
 assert app.history_tree.yview()[0]>0, 'History rows must scroll'
 assert rx.yview()==saved_rx and settings.yview()==saved_settings, 'inactive tabs remain unchanged'
 app.history_tree.yview_moveto(0);app.history_tree.yview_scroll(3,'units');expected=app.history_tree.yview()
 app.history_tree.yview_moveto(0);wheel(app.history_tree)
 assert app.history_tree.yview()==expected, 'table should scroll exactly once'
 app.history_tree.yview_moveto(0);wheel(app.history_tab)
 assert app.history_tree.yview()[0]>0, 'History blank areas scroll list'
 select(app.template_tab);saved_history=app.history_tree.yview();settings.yview_moveto(0);app.update()
 old_outer=outer.yview();wheel(app.template_editor.settings_panel)
 assert settings.yview()[0]>0, 'Template settings labels/frames scroll nested panel'
 assert outer.yview()==old_outer, 'nested panel must not scroll parent twice'
 assert rx.yview()==saved_rx and app.history_tree.yview()==saved_history
 old=(outer.yview(),settings.yview(),app.template_editor.preview_canvas.yview());wheel(app.template_editor.preview_canvas)
 assert (outer.yview(),settings.yview(),app.template_editor.preview_canvas.yview())!=old, 'Template preview area must scroll visible page or settings'
 select(app.new_rx_tab);old=rx.yview();wheel(app.p_first)
 assert rx.yview()[0]>old[0], 'switching tabs must route correctly without hover event'
 # Controls created after startup acquire the same routing on Map.
 dynamic=ttk.Label(app.p_first.master,text='Dynamic test');dynamic.grid(row=20,column=0);app.update()
 old=rx.yview();wheel(dynamic);assert rx.yview()[0]>old[0], 'dynamic controls'
 rx.yview_moveto(0);app.update();app.p_first.event_generate('<Button-5>');app.update()
 assert rx.yview()[0]>0, 'Linux wheel down'
 app.p_first.event_generate('<Button-4>');app.update();assert rx.yview()[0]==0, 'Linux wheel up'
 assert not errors,errors
 print('PASS: all tabs, nested settings, table single-scroll, blank areas, dynamic widgets, unchanged combo values, tab isolation, touchpad deltas, Linux wheel events')
finally:app.destroy()
