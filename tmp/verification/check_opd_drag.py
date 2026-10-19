import sys,uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from ereseta_local import config,database as db
from ereseta_local.app import EresetaApp
from ereseta_local.opd_layout import signature_box
from ereseta_local.opd_pdf import opd_pdf_bytes
from reportlab.pdfgen.canvas import Canvas
root=Path(__file__).resolve().parent;config.DB_FILE=str(root/(uuid.uuid4().hex+'.db'));db.init_db()
app=EresetaApp();app.update();editor=app.opd_layout_editor;app.opd_editor.open_layout()
def settle():app.after(400,app.quit);app.mainloop();app.update()
def event(x,y):return SimpleNamespace(x=x-editor.canvas.canvasx(0),y=y-editor.canvas.canvasy(0))
try:
 settle();editor.zoom_signature();settle();assert editor.zoom.get()=='200%'
 left,top,right,bottom=editor.signature_bounds
 start=event((left+right)/2,(top+bottom)/2);editor.start_drag(start);assert editor.drag is not None
 end=SimpleNamespace(x=start.x-35,y=start.y-50);editor.move_drag(end);editor.end_drag(end);settle()
 layout,page=editor.collect();assert layout['signature_x'] is not None and layout['signature_y'] is not None
 original=(layout['signature_x'],layout['signature_y']);editor.save();assert db.get_setting('opd_layout')['signature_x']==original[0]
 editor.zoom.set('Fit');settle();assert tuple(editor.collect()[0][k] for k in ('signature_x','signature_y'))==original
 # Actual PDF must use the same rectangle as the editor.
 draft=editor.sample(layout,page);draft['include_signature']=True;draft['physician']['signature_path']=str(root/'opd-test-signature.png')
 captured=[];original_draw=Canvas.drawImage
 def draw(self,image,x,y,**kwargs):
  captured.append((x,y,kwargs['width'],kwargs['height']));return original_draw(self,image,x,y,**kwargs)
 with patch.object(Canvas,'drawImage',draw):opd_pdf_bytes(draft)
 x,y,w,h=signature_box(layout,page['width']*72,page['height']*72)
 assert captured[-1]==(x,page['height']*72-y-h,w,h),captured[-1]
 editor.values['doctor_position'].set('Left');settle();assert editor.collect()[0]['signature_x'] is None
 editor.defaults();assert editor.collect()[0]['signature_x'] is None
 print('PASS: drag at 200% with scrolling, saved normalized position, zoom stability, exact PDF rectangle, preset/default reset')
finally:app.destroy()
