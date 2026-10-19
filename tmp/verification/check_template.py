import sys,uuid,math
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from PIL import Image,ImageDraw,ImageGrab
from ereseta_local import config,database as db
from ereseta_local.app import EresetaApp
from ereseta_local.template_editor import TemplateEditor
from ereseta_local.pdf_generator import generate_pdf,generate_template_preview
from reportlab.pdfgen.canvas import Canvas
root=Path(__file__).resolve().parent
config.DB_FILE=str(root/(uuid.uuid4().hex+'.db'));config.OUTPUT_DIR=str(root);db.init_db()
sig=root/'editor-test-signature.png';im=Image.new('RGBA',(420,110),(255,255,255,0));d=ImageDraw.Draw(im);d.text((35,40),'TEST E-SIGNATURE',fill='navy');d.line([(30,80),(350,80)],fill='navy',width=3);im.save(sig)
ph=db.find_or_create_physician('Sample Doctor','123','456',str(sig))
app=EresetaApp();app.notebook.select(app.template_tab);app.update()
errors=[];app.report_callback_exception=lambda *args:errors.append(args)
e=app.template_editor;e.preview_doctor.set('Dr. Sample Doctor');e.logo_enabled_var.set(False);e.rx_enabled_var.set(False);app.update()
try:
 assert e._signature_path()==str(sig) and 'sig' in e._image_boxes
 old=(e.sig_x_var.get(),e.sig_y_var.get())
 left,top,right,bottom=e._image_boxes['sig'];cx=int((left+right)/2);cy=int((top+bottom)/2)
 e.preview_canvas.event_generate('<ButtonPress-1>',x=cx,y=cy)
 e.preview_canvas.event_generate('<B1-Motion>',x=cx-30,y=cy-40)
 e.preview_canvas.event_generate('<ButtonRelease-1>',x=cx-30,y=cy-40);app.update()
 assert e.sig_x_var.get()<old[0] and e.sig_y_var.get()<old[1], 'drag moves signature'
 e._resize_image(1.1);e._move_image(-10,-10);app.update();assert e.sig_x_var.get()==0 and e.sig_y_var.get()==0
 e._move_image(10,10);app.update();assert math.isclose(e.sig_x_var.get()+e.sig_w_var.get(),1)
 e._place_signature();app.update()
 template=e._persist_template();assert template is not None
 cfg=template['signature_img'];assert math.isclose(cfg['y_pct'],1-e.sig_y_var.get()-e.sig_h_var.get())
 assert db.get_all_physicians()[0]['signature_path']==str(sig)
 fresh=TemplateEditor(app.template_tab,app);assert math.isclose(fresh.sig_y_var.get(),e.sig_y_var.get());fresh.destroy()
 calls=[];original=Canvas.drawImage
 def capture(self,image,x,y,*args,**kwargs):
  calls.append((x,y,kwargs.get('width'),kwargs.get('height')))
  return original(self,image,x,y,*args,**kwargs)
 with patch.object(Canvas,'drawImage',capture):
  preview=generate_template_preview(signature_path=e._signature_path())
 assert len(calls)==1,calls
 expected=(cfg['x_pct']*5.5*72,cfg['y_pct']*8.5*72,cfg['w_pct']*5.5*72,cfg['h_pct']*8.5*72)
 assert all(math.isclose(a,b) for a,b in zip(calls[0],expected)), (calls,expected)
 pid=db.find_or_create_patient('Example','','Patient',35,'Female','Sample address','Single')
 rx,_=db.save_prescription(pid,ph,'Sample follow-up',[dict(name='TEST MEDICINE',dosage='',quantity='10',instructions='Sample instructions')])
 calls.clear()
 with patch.object(Canvas,'drawImage',capture):actual=generate_pdf(rx)
 assert len(calls)==1 and all(math.isclose(a,b) for a,b in zip(calls[0],expected))
 e.sig_enabled_var.set(False);e._persist_template();calls.clear()
 with patch.object(Canvas,'drawImage',capture):generate_template_preview(signature_path=str(sig))
 assert not calls,'hidden signatures must not print'
 e.sig_enabled_var.set(True);e._persist_template();generate_template_preview(signature_path=str(sig))
 app.geometry('860x660');app.update()
 assert e.preview_canvas.winfo_width()>150
 assert e.winfo_rootx()+e.winfo_width()<=app.winfo_rootx()+app.winfo_width()
 app.geometry('1080x820');app.attributes('-topmost',True);app.lift();app.focus_force();app.update();app.after(250,app.quit);app.mainloop()
 ImageGrab.grab(bbox=(app.winfo_rootx(),app.winfo_rooty(),app.winfo_rootx()+app.winfo_width(),app.winfo_rooty()+app.winfo_height())).save(root/'template-editor.png')
 assert not errors,errors
 print('PASS: signature dragging, resizing, bounds, placement shortcut, save/reload, doctor ownership, matching preview/actual PDF coordinates, hide signature, responsive layout')
 print('PDF:',preview)
finally:app.destroy()
