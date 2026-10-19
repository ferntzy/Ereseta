import sys,uuid
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from ereseta_local import config,database as db
from ereseta_local.pdf_generator import prescription_pdf_bytes
from reportlab.pdfgen.canvas import Canvas
from reportlab.pdfbase.pdfmetrics import stringWidth
import pypdfium2 as pdfium
root=Path(__file__).resolve().parent
config.DB_FILE=str(root/(uuid.uuid4().hex+'.db'));db.init_db()
patient=dict(first_name='Sample',middle_name='',last_name='Patient',age=30,sex='Female',civil_status='Single',address='Sample address')
physician=dict(name='Dr. Sample',license_no='',ptr_no='',signature_path='')
items=[dict(name='Medicine with a long name that must wrap before reaching the handwriting space',quantity='',instructions='Sample instructions'),dict(name='Second medicine',quantity='10',instructions='Sample instructions')]
left=[];right=[]
original_left=Canvas.drawString;original_right=Canvas.drawRightString

def draw_left(self,x,y,text,*args,**kwargs):
 left.append((x,y,text,self._fontsize));return original_left(self,x,y,text,*args,**kwargs)
def draw_right(self,x,y,text,*args,**kwargs):
 right.append((x,y,text));return original_right(self,x,y,text,*args,**kwargs)
with patch.object(Canvas,'drawString',draw_left),patch.object(Canvas,'drawRightString',draw_right):
 data=prescription_pdf_bytes(patient,physician,items)
marker=next(row for row in left if row[2]=='#')
filled=next(row for row in left if row[2]=='#10')
assert filled[0]==marker[0], 'Blank and filled quantities must share the same left edge'
assert 0.7*72-stringWidth('#','Helvetica-Bold',marker[3])>=40
name_lines=[row for row in left if row[1]==marker[1] and row[2]!='#']
assert name_lines and all(row[0]+stringWidth(row[2],'Helvetica-Bold',row[3])<=marker[0]-8 for row in name_lines)
(root/'handwriting-quantity.pdf').write_bytes(data)
doc=pdfium.PdfDocument(data);page=doc[0];bitmap=page.render(scale=1.5);bitmap.to_pil().save(root/'handwriting-quantity.png');bitmap.close();page.close();doc.close()
print('PASS: blank and filled # markers align; handwriting space retained; long medicine name stays outside quantity area')
