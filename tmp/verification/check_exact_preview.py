import sys,uuid,io,hashlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from PIL import Image,ImageDraw,ImageChops,ImageTk,ImageGrab
import pypdfium2 as pdfium
from ereseta_local import config,database as db
from ereseta_local.app import EresetaApp
from ereseta_local.pdf_generator import _asset_reader,generate_template_preview,generate_pdf,template_pdf_bytes
root=Path(__file__).resolve().parent
config.DB_FILE=str(root/(uuid.uuid4().hex+'.db'));config.OUTPUT_DIR=str(root);db.init_db()
# Opaque border plus enclosed white detail: only the border should disappear.
asset=root/'white-edge-test.png';im=Image.new('RGBA',(120,80),'white');d=ImageDraw.Draw(im);d.rectangle((30,20,90,60),fill='black');d.rectangle((40,30,80,50),fill='white');im.save(asset)
original=asset.read_bytes()
clean=_asset_reader(str(asset),True)._image
assert clean.getpixel((0,0))[3]==0 and clean.getpixel((50,40))[3]==255
assert clean.getpixel((30,20))[3]==255 and asset.read_bytes()==original
assert _asset_reader(str(asset),False)._image.getpixel((0,0))[3]==255
alpha=root/'alpha-test.png';im=Image.new('RGBA',(40,40),(20,20,20,0));im.putpixel((20,20),(0,0,0,100));im.save(alpha)
assert _asset_reader(str(alpha),True)._image.getpixel((20,20))[3]==100
ph=db.find_or_create_physician('Example Doctor','123','456',str(asset))
app=EresetaApp();app.notebook.select(app.template_tab);app.attributes('-topmost',True);app.update()
errors=[];app.report_callback_exception=lambda *args:errors.append(args)
e=app.template_editor;e.preview_doctor.set('Dr. Example Doctor');e.logo_enabled_var.set(False);e.rx_enabled_var.set(False)
def settle():app.after(140,app.quit);app.mainloop();app.update()
def raster(data,scale):
 doc=pdfium.PdfDocument(data);page=doc[0];bitmap=page.render(scale=scale);im=bitmap.to_pil().copy();bitmap.close();page.close();doc.close();return im
try:
 settle();assert hasattr(e,'_pdf_photo'),e.status_var.get()
 e.guides_var.set(False);e.zoom_var.set('100%');settle()
 template=e._collect_template();export=generate_template_preview(str(asset),template)
 # Pixel equality between editor backing image and exported PDF, same scale.
 exported=raster(Path(export).read_bytes(),e._render_scale)
 shown=ImageTk.getimage(e._pdf_photo).convert('RGB')
 assert exported.size==shown.size and ImageChops.difference(exported.convert('RGB'),shown).getbbox() is None
 assert e._paper[2:]==(528,816),e._paper
 e.zoom_var.set('200%');e.guides_var.set(True);settle()
 assert e.preview_canvas.yview()[1]<1 and e.preview_canvas.xview()[1]<1
 e.preview_canvas.xview_moveto(.3);e.preview_canvas.yview_moveto(.7);app.update()
 # Move signature using viewport coordinates after zooming and scrolling.
 left,top,right,bottom=e._image_boxes['sig'];cx=(left+right)/2-e.preview_canvas.canvasx(0);cy=(top+bottom)/2-e.preview_canvas.canvasy(0)
 old=e.sig_x_var.get(),e.sig_y_var.get()
 from types import SimpleNamespace
 e._start_drag(SimpleNamespace(x=cx,y=cy));e._drag_image(SimpleNamespace(x=cx-25,y=cy-30));e._end_drag();settle()
 assert e.sig_x_var.get()<old[0] and e.sig_y_var.get()<old[1]
 e._place_signature();e._persist_template();e.zoom_var.set('Fit');settle()
 assert e.preview_canvas.yview()==(0.0,1.0),e.preview_canvas.yview()
 # Production PDF uses the same rendering path and geometry as the template.
 pid=db.find_or_create_patient('SAMPLE','','PATIENT',35,'Female','SAMPLE ADDRESS','Single')
 medicines=[dict(name=m['name'],dosage=m.get('dosage',''),quantity=m.get('quantity',''),instructions=m.get('instructions','')) for m in e._collect_template()['preview_medicines']]
 sample_ph=db.find_or_create_physician('Sample physician','--','--',str(asset))
 rx,_=db.save_prescription(pid,sample_ph,'Sample follow-up note',medicines)
 actual=generate_pdf(rx);expected=template_pdf_bytes(e._collect_template(),str(asset))
 assert ImageChops.difference(raster(Path(actual).read_bytes(),1).convert('RGB'),raster(expected,1).convert('RGB')).getbbox() is None
 app.geometry('860x660');settle();assert e.winfo_rootx()+e.winfo_width()<=app.winfo_rootx()+app.winfo_width()
 app.geometry('1080x820');settle();app.lift();app.focus_force();settle()
 ImageGrab.grab(bbox=(app.winfo_rootx(),app.winfo_rooty(),app.winfo_rootx()+app.winfo_width(),app.winfo_rooty()+app.winfo_height())).save(root/'exact-editor.png')
 assert not errors,errors
 print('PASS: white-border removal, enclosed whites preserved, alpha preserved, source unchanged, pixel-identical editor/export/production rendering, 100% and 200% zoom, pan, zoomed drag, fit reset, minimum size')
finally:app.destroy()
